"""Synthetic procure-to-pay (P2P) event log with realistic, discoverable inefficiencies.

Real client logs can't be published, so this generator plants known problems (slow manual
approvals, vendor price mismatches, PO changes, weekly payment batching) that the mining and ML
stages then have to find on their own.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

VENDORS = {
    # name: (category, lead_time_days, price_mismatch_rate)
    "Apex Components": ("IT Hardware", 6, 0.28),
    "Northwind Supplies": ("Office Supplies", 3, 0.04),
    "BlueRiver Logistics": ("Logistics", 4, 0.10),
    "Kaveri Industrial": ("Raw Materials", 10, 0.22),
    "Orbit Software": ("Software & Services", 2, 0.05),
    "Sahyadri Facilities": ("Facilities", 5, 0.12),
    "Indus Steel Traders": ("Raw Materials", 12, 0.18),
    "Pixel Peripherals": ("IT Hardware", 7, 0.08),
    "Greenleaf Stationers": ("Office Supplies", 3, 0.03),
    "Meridian Consulting": ("Software & Services", 3, 0.06),
}
REGIONS = ["North", "South", "West"]
HAPPY_PATH = [
    "Create Requisition", "Approve Requisition", "Create Purchase Order", "Send PO to Vendor",
    "Receive Goods", "Receive Invoice", "Three-Way Match", "Approve Payment", "Pay Invoice",
]


def _business_shift(ts: pd.Timestamp) -> pd.Timestamp:
    """Push weekend timestamps to Monday 10:00."""
    if ts.weekday() >= 5:
        ts = (ts + pd.Timedelta(days=7 - ts.weekday())).normalize() + pd.Timedelta(hours=10)
    return ts


def generate_event_log(n_cases: int = 2400, seed: int = 42, start: str = "2026-01-01",
                       end: str = "2026-09-30") -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    vendor_names = list(VENDORS)
    span = (pd.Timestamp(end) - pd.Timestamp(start)).total_seconds()
    rows = []

    for i in range(n_cases):
        case_id = f"PR-{100000 + i}"
        vendor = vendor_names[rng.choice(len(vendor_names), p=np.array([14, 12, 9, 10, 8, 9, 8, 10, 11, 9]) / 100)]
        category, lead_days, mismatch_rate = VENDORS[vendor]
        region = REGIONS[rng.integers(3)]
        channel = "Catalog" if rng.random() < (0.6 if category == "Office Supplies" else 0.38) else "Manual"
        amount = float(np.clip(rng.lognormal(np.log(65000), 1.05), 1500, 4_000_000))
        manual = channel == "Manual"
        t = _business_shift(pd.Timestamp(start) + pd.Timedelta(seconds=float(rng.uniform(0, span))))
        t = t.normalize() + pd.Timedelta(hours=float(rng.uniform(9, 18)))
        attrs = dict(vendor=vendor, category=category, region=region, channel=channel, amount=round(amount, 2))

        def emit(activity: str, hours: float, resource: str) -> None:
            nonlocal t
            t = _business_shift(t + pd.Timedelta(hours=float(hours)))
            rows.append(dict(case_id=case_id, activity=activity, timestamp=t.floor("s"), resource=resource, **attrs))

        emit("Create Requisition", 0, "Requester")
        emit("Approve Requisition", rng.exponential(34 if manual else 7) + (24 if region == "North" else 0), "Line Manager")
        if amount > 500_000:
            emit("Second-Level Approval", rng.exponential(80), "Finance Controller")
        emit("Create Purchase Order", rng.exponential(22 if manual else 5), "Buyer")
        emit("Send PO to Vendor", rng.exponential(3), "Buyer")
        if rng.random() < (0.16 if manual else 0.05):
            emit("Change Purchase Order", rng.exponential(30), "Buyer")
            emit("Send PO to Vendor", rng.exponential(3), "Buyer")

        goods_wait = rng.gamma(4, lead_days * 24 / 4)
        invoice_first = rng.random() < 0.15
        if invoice_first:
            emit("Receive Invoice", goods_wait * 0.6, "AP Clerk")
            emit("Receive Goods", goods_wait * 0.4, "Warehouse")
        else:
            emit("Receive Goods", goods_wait, "Warehouse")
            emit("Receive Invoice", rng.exponential(40), "AP Clerk")

        emit("Three-Way Match", rng.exponential(10 if not manual else 20), "AP Clerk")
        if rng.random() < mismatch_rate + (0.05 if manual else 0):
            emit("Resolve Price Mismatch", rng.exponential(110), "AP Clerk")
            emit("Three-Way Match", rng.exponential(8), "AP Clerk")
        emit("Approve Payment", rng.exponential(48 if manual else 20) + (30 if amount > 500_000 else 0), "AP Manager")
        # Weekly payment run on Fridays at 16:00.
        days_to_friday = (4 - t.weekday()) % 7 or 7
        pay_at = t.normalize() + pd.Timedelta(days=days_to_friday, hours=16)
        emit("Pay Invoice", (pay_at - t).total_seconds() / 3600, "Treasury")

    df = pd.DataFrame(rows)
    return df.sort_values(["case_id", "timestamp"], kind="stable").reset_index(drop=True)
