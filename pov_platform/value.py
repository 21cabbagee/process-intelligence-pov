"""Proof-of-value model: turns mined process facts into annualised savings per improvement lever.

Volumes (how many manual cases, mismatches, matches, eligible spend) come from the event log;
unit costs and adoption rates are assumptions to agree with the business sponsor.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd


@dataclass
class ValueAssumptions:
    annual_cases: int = 25_000                 # client's full annual requisition volume
    hourly_cost: float = 750.0                 # INR, fully loaded
    manual_touch_minutes: float = 45.0         # handling time per manual-channel requisition
    catalog_touch_minutes: float = 12.0
    mismatch_rework_hours: float = 2.5         # AP effort per price mismatch
    match_minutes: float = 18.0                # manual three-way match effort
    early_pay_discount: float = 0.015          # 1.5% for paying within 10 days
    discount_days: float = 10.0
    discount_rate: float = 0.10                # for NPV
    run_cost_annual: float = 900_000.0


LEVERS = {
    "catalog_first": {"name": "Catalog-first buying", "adoption": 0.5, "build_cost": 1_200_000},
    "price_sync": {"name": "Vendor price-master sync", "adoption": 0.6, "build_cost": 800_000},
    "touchless_match": {"name": "Touchless three-way match", "adoption": 0.7, "build_cost": 1_500_000},
    "early_payment": {"name": "Early-payment discount capture", "adoption": 0.25, "build_cost": 600_000},
}


def value_drivers(cases: pd.DataFrame, events: pd.DataFrame) -> dict:
    """Per-case rates measured on the sample log; the business case scales them to full volume."""
    n = len(cases)
    inv = events[events["activity"] == "Receive Invoice"].groupby("case_id")["timestamp"].min()
    pay = events[events["activity"] == "Pay Invoice"].groupby("case_id")["timestamp"].max()
    days_inv_to_pay = ((pay - inv).dt.total_seconds() / 86400).reindex(cases["case_id"]).to_numpy()
    return {
        "sample_cases": n,
        "manual_share": round(float((cases["channel"] == "Manual").mean()), 4),
        "mismatch_rate": round(float(cases["price_mismatch"].mean()), 4),
        "matches_per_case": round(float((events["activity"] == "Three-Way Match").sum() / n), 4),
        "spend_per_case": round(float(cases["amount"].mean()), 2),
        "late_for_discount_spend_share": round(float(cases.loc[days_inv_to_pay > 10, "amount"].sum() / cases["amount"].sum()), 4),
        "median_days_invoice_to_pay": round(float(pd.Series(days_inv_to_pay).median()), 1),
    }


def lever_savings(d: dict, a: ValueAssumptions, adoption: dict[str, float] | None = None) -> dict[str, float]:
    adoption = {k: v["adoption"] for k, v in LEVERS.items()} | (adoption or {})
    n = a.annual_cases
    hours = {
        "catalog_first": n * d["manual_share"] * adoption["catalog_first"] * (a.manual_touch_minutes - a.catalog_touch_minutes) / 60,
        "price_sync": n * d["mismatch_rate"] * adoption["price_sync"] * a.mismatch_rework_hours,
        "touchless_match": n * d["matches_per_case"] * adoption["touchless_match"] * a.match_minutes / 60,
        "early_payment": 0.0,
    }
    savings = {k: h * a.hourly_cost for k, h in hours.items()}
    late_spend = n * d["spend_per_case"] * d["late_for_discount_spend_share"]
    savings["early_payment"] = late_spend * adoption["early_payment"] * a.early_pay_discount
    return {"hours": hours, "savings": savings}


def business_case(d: dict, a: ValueAssumptions = ValueAssumptions(), adoption: dict[str, float] | None = None) -> dict:
    adoption = {k: v["adoption"] for k, v in LEVERS.items()} | (adoption or {})
    s = lever_savings(d, a, adoption)
    annual = sum(s["savings"].values())
    build = sum(v["build_cost"] for k, v in LEVERS.items() if adoption[k] > 0)  # unused levers cost nothing
    net = annual - a.run_cost_annual
    npv = -build + sum(net / (1 + a.discount_rate) ** y for y in (1, 2, 3))
    return {
        "levers": [{"key": k, "name": LEVERS[k]["name"], "hours_per_year": round(s["hours"][k]),
                    "saving_per_year": round(s["savings"][k]), "build_cost": LEVERS[k]["build_cost"]} for k in LEVERS],
        "annual_saving": round(annual),
        "annual_net": round(net),
        "fte_equivalent": round(sum(s["hours"].values()) / 1800, 1),
        "build_cost": build,
        "payback_months": round(build / net * 12, 1) if net > 0 else None,
        "npv_3y": round(npv),
        "assumptions": asdict(a),
    }
