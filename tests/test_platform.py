import pandas as pd
import pytest

from pov_platform import mining
from pov_platform.generator import HAPPY_PATH, generate_event_log
from pov_platform.model import train_breach_model
from pov_platform.pipeline import build_case_table, load_event_log
from pov_platform.value import LEVERS, ValueAssumptions, business_case, value_drivers


@pytest.fixture(scope="module")
def log():
    events, report = load_event_log(generate_event_log(n_cases=900, seed=3))
    return events, build_case_table(events), report


def test_generator_is_deterministic():
    a, b = generate_event_log(50, seed=1), generate_event_log(50, seed=1)
    pd.testing.assert_frame_equal(a, b)
    assert set(HAPPY_PATH) <= set(a["activity"])


def test_validation_cleans_and_maps_columns():
    raw = generate_event_log(20, seed=2).rename(columns={"case_id": "CaseKey", "activity": "Event", "timestamp": "Time"})
    raw = pd.concat([raw, raw.iloc[:5]])
    raw.loc[len(raw)] = {**raw.iloc[0].to_dict(), "Event": None}
    df, report = load_event_log(raw.reset_index(drop=True), column_map={"CaseKey": "case_id", "Event": "activity", "Time": "timestamp"})
    assert report.duplicates_removed == 5 and report.null_rows_removed == 1 and report.cases == 20
    with pytest.raises(ValueError):
        load_event_log(pd.DataFrame({"x": [1]}))


def test_case_table(log):
    events, cases, _ = log
    assert len(cases) == events["case_id"].nunique()
    assert (cases["cycle_days"] > 0).all()
    assert cases.loc[cases["price_mismatch"], "rework"].ge(1).all()


def test_dfg_flow_is_conserved(log):
    events, cases, _ = log
    edges = mining.directly_follows(events)
    inner = edges[~edges["source"].str.startswith("●") & ~edges["target"].str.startswith("■")]
    assert inner["count"].sum() == len(events) - len(cases)
    assert edges.loc[edges["source"] == "●start", "count"].sum() == len(cases)


def test_mining_finds_planted_problems(log):
    _, cases, _ = log
    by_channel = mining.segment_breakdown(cases, "channel").set_index("channel")
    assert by_channel.loc["Manual", "median_cycle_days"] > by_channel.loc["Catalog", "median_cycle_days"]
    by_vendor = mining.segment_breakdown(cases, "vendor").sort_values("mismatch_rate", ascending=False)
    assert "Apex Components" in by_vendor["vendor"].head(3).tolist()


def test_conformance_bounds(log):
    events, _, _ = log
    c = mining.conformance(events)
    assert 0 < c["happy_path_rate"] <= c["order_fitness"] <= 1


def test_breach_model_beats_chance(log):
    _, cases, _ = log
    m = train_breach_model(cases)
    assert m["models"][m["best"]]["roc_auc"] > 0.7
    assert m["top20_breach_capture"] > 0.2  # better than random (20%)


def test_business_case_math(log):
    events, cases, _ = log
    d = value_drivers(cases, events)
    zero = business_case(d, ValueAssumptions(), adoption={k: 0 for k in LEVERS})
    assert zero["annual_saving"] == 0 and zero["payback_months"] is None
    full = business_case(d, ValueAssumptions())
    assert full["annual_saving"] > 0 and full["payback_months"] > 0
    doubled = business_case(d, ValueAssumptions(annual_cases=50_000))
    assert doubled["annual_saving"] == pytest.approx(2 * full["annual_saving"], rel=1e-6)
