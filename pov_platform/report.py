"""Runs the full proof-of-value pipeline and exports dashboard-ready JSON."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from . import mining
from .generator import HAPPY_PATH, generate_event_log
from .model import train_breach_model
from .pipeline import build_case_table, load_event_log
from .value import LEVERS, ValueAssumptions, business_case, value_drivers

# Fixed process-map layout (column, row) so the dashboard draws a readable map.
LAYOUT = {
    "●start": (0, 1), "Create Requisition": (1, 1), "Approve Requisition": (2, 1), "Second-Level Approval": (2.5, 0),
    "Create Purchase Order": (3, 1), "Send PO to Vendor": (4, 1), "Change Purchase Order": (4, 2),
    "Receive Goods": (5, 1), "Receive Invoice": (6, 1), "Three-Way Match": (7, 1), "Resolve Price Mismatch": (7, 2),
    "Approve Payment": (8, 1), "Pay Invoice": (9, 1), "■end": (10, 1),
}


def _records(df: pd.DataFrame) -> list[dict]:
    return json.loads(df.to_json(orient="records"))


def run(event_log: str | Path | pd.DataFrame | None = None, sla_days: float = 21.0) -> dict:
    raw = generate_event_log() if event_log is None else event_log
    events, validation = load_event_log(raw)
    cases = build_case_table(events, sla_days=sla_days)
    edges = mining.directly_follows(events)
    model = train_breach_model(cases)
    drivers = value_drivers(cases, events)
    monthly = (cases.groupby("start_month")
               .agg(cases=("case_id", "size"), median_cycle_days=("cycle_days", "median"), breach_rate=("sla_breach", "mean"))
               .reset_index())
    return {
        "meta": {"process": "Procure-to-Pay", "sla_days": sla_days, "events": len(events), "cases": len(cases),
                 "from": str(cases["start"].min().date()), "to": str(cases["end"].max().date()),
                 "validation": validation.__dict__, "reference_model": HAPPY_PATH},
        "kpis": {
            "median_cycle_days": round(float(cases["cycle_days"].median()), 1),
            "p90_cycle_days": round(float(cases["cycle_days"].quantile(0.9)), 1),
            "sla_breach_rate": round(float(cases["sla_breach"].mean()), 3),
            "rework_rate": round(float((cases["rework"] > 0).mean()), 3),
            "price_mismatch_rate": round(float(cases["price_mismatch"].mean()), 3),
            "spend": round(float(cases["amount"].sum())),
            "variants": int(cases["variant"].nunique()),
        },
        "conformance": mining.conformance(events),
        "process_map": {"edges": _records(edges.round(2)), "layout": LAYOUT,
                        "activities": _records(mining.activity_stats(events).round(2))},
        "variants": _records(mining.variants(cases).round(4)),
        "bottlenecks": _records(mining.bottlenecks(edges).round(2)),
        "segments": {by: _records(mining.segment_breakdown(cases, by).round(4)) for by in ("vendor", "channel", "region", "category")},
        "monthly": _records(monthly.round(4)),
        "cycle_histogram": _records(pd.cut(cases["cycle_days"], bins=list(range(0, 61, 3)) + [1e9], right=False)
                                    .value_counts(sort=False).rename_axis("bin").reset_index(name="cases")
                                    .assign(bin=lambda d: d["bin"].astype(str))),
        "model": {k: v for k, v in model.items() if k != "pipeline"},
        "value": {"drivers": drivers, "levers_meta": LEVERS, "baseline": business_case(drivers, ValueAssumptions())},
    }


def export(out_dir: str | Path, **kwargs) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    result = run(**kwargs)
    (out / "dashboard.json").write_text(json.dumps(result, indent=1, default=str))
    return result
