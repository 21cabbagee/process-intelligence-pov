"""CLI.

    python -m pov_platform                      # synthetic P2P log -> docs/data/dashboard.json
    python -m pov_platform my_log.csv           # your own log (case_id, activity, timestamp, ...)
"""

import sys
from pathlib import Path

from .report import export

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    source = sys.argv[1] if len(sys.argv) > 1 else None
    r = export(ROOT / "docs" / "data", event_log=source)
    if source is None:  # publish a small sample of the synthetic log so others can inspect the input format
        from .generator import generate_event_log

        log = generate_event_log()
        log[log["case_id"].isin(log["case_id"].unique()[:300])].to_csv(ROOT / "data" / "p2p_event_log_sample.csv", index=False)
    k, v, m = r["kpis"], r["value"]["baseline"], r["model"]
    print(f"{r['meta']['cases']} cases, {r['meta']['events']} events, {k['variants']} variants")
    print(f"Median cycle {k['median_cycle_days']} d | SLA breach {k['sla_breach_rate']:.0%} | rework {k['rework_rate']:.0%}")
    print(f"Happy-path conformance {r['conformance']['happy_path_rate']:.0%}")
    print(f"Top bottleneck: {r['bottlenecks'][0]['source']} -> {r['bottlenecks'][0]['target']}")
    print(f"SLA-breach model: {m['best']} AUC {m['models'][m['best']]['roc_auc']}, top-20% capture {m['top20_breach_capture']:.0%}")
    print(f"Business case: INR {v['annual_saving']:,}/yr, payback {v['payback_months']} months, 3y NPV INR {v['npv_3y']:,}")


if __name__ == "__main__":
    main()
