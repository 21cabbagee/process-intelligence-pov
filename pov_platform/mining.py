"""Process discovery and diagnostics: directly-follows graph, variants, bottlenecks, conformance."""

from __future__ import annotations

import pandas as pd

from .generator import HAPPY_PATH
from .pipeline import add_waits


def directly_follows(df: pd.DataFrame) -> pd.DataFrame:
    w = add_waits(df).dropna(subset=["prev_activity"])
    edges = (w.groupby(["prev_activity", "activity"])["wait_hours"]
             .agg(count="size", median_wait_h="median", p90_wait_h=lambda s: s.quantile(0.9))
             .reset_index().rename(columns={"prev_activity": "source", "activity": "target"}))
    starts = df.groupby("case_id")["activity"].first().value_counts()
    ends = df.groupby("case_id")["activity"].last().value_counts()
    extra = [{"source": "●start", "target": a, "count": int(n), "median_wait_h": 0.0, "p90_wait_h": 0.0} for a, n in starts.items()]
    extra += [{"source": a, "target": "■end", "count": int(n), "median_wait_h": 0.0, "p90_wait_h": 0.0} for a, n in ends.items()]
    return pd.concat([edges, pd.DataFrame(extra)], ignore_index=True).sort_values("count", ascending=False)


def activity_stats(df: pd.DataFrame) -> pd.DataFrame:
    w = add_waits(df)
    return (w.groupby("activity").agg(events=("case_id", "size"), cases=("case_id", "nunique"),
                                      median_wait_h=("wait_hours", "median"))
            .reset_index().sort_values("events", ascending=False))


def variants(cases: pd.DataFrame, top: int = 10) -> pd.DataFrame:
    v = (cases.groupby("variant").agg(cases=("case_id", "size"), median_cycle_days=("cycle_days", "median"),
                                      breach_rate=("sla_breach", "mean"))
         .reset_index().sort_values("cases", ascending=False))
    v["share"] = v["cases"] / len(cases)
    v["cumulative_share"] = v["share"].cumsum()
    v["steps"] = v["variant"].str.count("→") + 1
    return v.head(top)


def bottlenecks(edges: pd.DataFrame, top: int = 8) -> pd.DataFrame:
    """Transitions ranked by total waiting time they add across all cases."""
    e = edges[~edges["source"].str.startswith("●") & ~edges["target"].str.startswith("■")].copy()
    e["total_wait_days"] = e["count"] * e["median_wait_h"] / 24
    return e.sort_values("total_wait_days", ascending=False).head(top)


def conformance(df: pd.DataFrame, reference: list[str] = HAPPY_PATH) -> dict:
    """Simple trace-based conformance against the reference (happy-path) model."""
    traces = df.groupby("case_id")["activity"].agg(list)
    ref = tuple(reference)
    exact = traces.map(lambda t: tuple(t) == ref)

    def is_subsequence(trace: list[str]) -> bool:
        it = iter(trace)
        return all(any(a == b for b in it) for a in ref)

    order_ok = traces.map(is_subsequence)
    invoice_before_goods = traces.map(
        lambda t: "Receive Invoice" in t and "Receive Goods" in t and t.index("Receive Invoice") < t.index("Receive Goods"))
    loops = traces.map(lambda t: len(t) != len(set(t)))
    return {
        "cases": int(len(traces)),
        "happy_path_rate": round(float(exact.mean()), 4),
        "order_fitness": round(float(order_ok.mean()), 4),
        "invoice_before_goods_rate": round(float(invoice_before_goods.mean()), 4),
        "rework_loop_rate": round(float(loops.mean()), 4),
        "extra_approval_rate": round(float(traces.map(lambda t: "Second-Level Approval" in t).mean()), 4),
    }


def segment_breakdown(cases: pd.DataFrame, by: str) -> pd.DataFrame:
    return (cases.groupby(by).agg(cases=("case_id", "size"), median_cycle_days=("cycle_days", "median"),
                                  breach_rate=("sla_breach", "mean"), mismatch_rate=("price_mismatch", "mean"),
                                  spend=("amount", "sum"))
            .reset_index().sort_values("median_cycle_days", ascending=False))
