"""Ingestion, validation and case-level feature engineering for any event log.

Expected columns: case_id, activity, timestamp (+ any case attributes). Column names from other
tools (Celonis, SAP extracts, CSV exports) can be mapped via ``column_map``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

REQUIRED = ("case_id", "activity", "timestamp")
REWORK_ACTIVITIES = ("Change Purchase Order", "Resolve Price Mismatch")


@dataclass
class ValidationReport:
    rows_in: int
    rows_out: int
    duplicates_removed: int = 0
    null_rows_removed: int = 0
    cases: int = 0
    issues: list[str] = field(default_factory=list)


def load_event_log(source: str | Path | pd.DataFrame, column_map: dict[str, str] | None = None
                   ) -> tuple[pd.DataFrame, ValidationReport]:
    df = source.copy() if isinstance(source, pd.DataFrame) else pd.read_csv(source)
    if column_map:
        df = df.rename(columns=column_map)
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"event log is missing required columns: {missing}")

    report = ValidationReport(rows_in=len(df), rows_out=0)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    nulls = df[list(REQUIRED)].isna().any(axis=1)
    report.null_rows_removed = int(nulls.sum())
    df = df[~nulls]
    dupes = df.duplicated(subset=list(REQUIRED))
    report.duplicates_removed = int(dupes.sum())
    df = df[~dupes].sort_values(["case_id", "timestamp"], kind="stable").reset_index(drop=True)
    report.rows_out, report.cases = len(df), df["case_id"].nunique()
    if report.null_rows_removed:
        report.issues.append(f"{report.null_rows_removed} rows with missing case/activity/timestamp dropped")
    if report.duplicates_removed:
        report.issues.append(f"{report.duplicates_removed} duplicate events dropped")
    return df, report


def build_case_table(df: pd.DataFrame, sla_days: float = 21.0) -> pd.DataFrame:
    """One row per case: timing, rework, variant and the case attributes."""
    g = df.groupby("case_id", sort=False)
    attrs = [c for c in df.columns if c not in ("activity", "timestamp", "resource", "case_id")]
    cases = g.agg(start=("timestamp", "min"), end=("timestamp", "max"), events=("activity", "size"))
    if attrs:
        cases = cases.join(g[attrs].first())
    cases["variant"] = g["activity"].agg(" → ".join)
    cases["cycle_days"] = (cases["end"] - cases["start"]).dt.total_seconds() / 86400
    cases["rework"] = g["activity"].agg(lambda s: int(s.isin(REWORK_ACTIVITIES).sum()))
    cases["price_mismatch"] = g["activity"].agg(lambda s: bool((s == "Resolve Price Mismatch").any()))
    cases["po_changed"] = g["activity"].agg(lambda s: bool((s == "Change Purchase Order").any()))
    cases["sla_breach"] = cases["cycle_days"] > sla_days
    cases["start_month"] = cases["start"].dt.to_period("M").astype(str)
    return cases.reset_index()


def add_waits(df: pd.DataFrame) -> pd.DataFrame:
    """Annotate each event with the previous activity and waiting time (hours) since it."""
    df = df.copy()
    df["prev_activity"] = df.groupby("case_id")["activity"].shift()
    df["wait_hours"] = df.groupby("case_id")["timestamp"].diff().dt.total_seconds() / 3600
    return df
