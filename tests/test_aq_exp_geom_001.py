"""AQ-EXP-GEOM-001 — OHLC 幾何驗證缺陷的實際受影響筆數。

公開部分只驗聚合檔自洽；真實掃描需要固定 source 與 producer，缺任一項即 skip。
真實那支同時是回歸測試：上游 valid_ohlc 若退化、讓幾何壞列通過，它會紅。
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "out" / "aq_exp_geom_001_ohlc_geometry.json"
R2_MANIFEST = ROOT / "out" / "aq_exp_data_001_r2_manifest.json"

ORIGINAL_ROW_COUNT = 458315
ALL_FOUR = 428102
FEATURES = ["MA120", "N60", "ATR14", "LOW20"]
TYPES = [
    "high_lt_low",
    "high_lt_max_open_close",
    "low_gt_min_open_close",
    "nonpositive_ohlc",
    "null_ohlc",
]


@pytest.fixture(scope="module")
def art():
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


def test_result_is_exact_zero_not_a_bound(art):
    r = art["result"]
    assert r["real_violating_rows_in_universe"] == 0
    assert r["is_exact"] is True
    assert r["violating_stocks_in_universe"] == 0
    assert r["violating_rows_by_year_in_universe"] == {}
    assert set(r["violations_by_type_in_universe"]) == set(TYPES)
    assert all(v == 0 for v in r["violations_by_type_in_universe"].values())


def test_zero_is_attributed_to_the_upstream_flag_not_to_clean_data(art):
    r = art["result"]
    # 全 panel 確實有壞列，只是全被上游擋掉；這兩件事不可混為一談。
    assert r["any_violation_whole_panel"] > 0
    assert r["violations_passing_source_valid_ohlc"] == 0
    assert r["violations_already_flagged_upstream"] == r["any_violation_whole_panel"]
    assert r["upstream_catch_rate_pct"] == 100.0
    assert art["defect_under_test"]["producer_has_independent_geometry_gate"] is False
    assert art["defect_under_test"]["defect_class"] == "LATENT_CONDITIONAL_ON_UPSTREAM_FLAG"


def test_panel_type_counts_are_consistent(art):
    r = art["result"]
    by_type = r["violations_by_type_whole_panel"]
    assert set(by_type) == set(TYPES)
    # 去重後的總數不得超過各型態相加，也不得小於任一型態。
    assert r["any_violation_whole_panel"] <= sum(by_type.values())
    assert r["any_violation_whole_panel"] >= max(by_type.values())
    assert sum(r["violations_by_year_whole_panel"].values()) == r["any_violation_whole_panel"]
    # PR #8 舉的 high<low 在真實來源一列都沒有。
    assert by_type["high_lt_low"] == 0
    assert r["high_lt_low_rows_anywhere"] == 0


def test_no_feature_aggregate_moves(art):
    imp = art["feature_aggregate_impact"]
    assert imp["rows_newly_unusable"] == 0
    assert sorted(imp["per_feature"]) == sorted(FEATURES)
    for name, blk in imp["per_feature"].items():
        assert blk["delta"] == {}, name
        assert blk["before"] == blk["after"], name
        assert blk["before"]["stock_days"] == ORIGINAL_ROW_COUNT, name
    assert imp["all_four_numeric_computable_before"] == ALL_FOUR
    assert imp["all_four_numeric_computable_after"] == ALL_FOUR
    assert imp["all_four_delta"] == 0
    # delta 為 0 時不得指名主導 feature。
    assert imp["dominant_feature_for_all_four_delta"] is None


def test_all_four_equals_ma120_numeric_in_the_recorded_baseline(art):
    per = art["feature_aggregate_impact"]["per_feature"]
    # MA120 是最窄的一項，四項交集等於它並非巧合；若哪天不等，baseline 有問題。
    assert per["MA120"]["before"]["numeric_computable"] == ALL_FOUR
    for name in FEATURES:
        assert per[name]["before"]["numeric_computable"] >= ALL_FOUR, name


def test_evidence_state_block_is_empty_by_definition(art):
    blk = art["evidence_state_of_violating_rows"]
    assert blk["applicable"] is False
    assert art["result"]["real_violating_rows_in_universe"] == 0


def test_residual_risk_is_recorded_as_blast_radius_not_as_an_error(art):
    rr = art["residual_risk"]
    assert rr["rows_that_would_enter_candidate_screen_if_upstream_flag_regressed"] > 0
    assert rr["stocks_affected_in_that_case"] > 0
    assert art["result"]["real_violating_rows_in_universe"] == 0


def test_does_not_retract_pr8(art):
    assert art["contradicts_pr8"] is False
    assert art["defect_under_test"]["producer_has_independent_geometry_gate"] is False


def test_gate_and_scope_are_not_relaxed(art):
    assert art["execution_authorized"] is False
    assert art["formal_research_gate"] == "BLOCKED_UNCONDITIONALLY"
    assert art["scope"] == "SOURCE_EVIDENCE"


def test_artifact_inputs_match_the_r2_manifest(art):
    man = json.loads(R2_MANIFEST.read_text(encoding="utf-8"))
    inp, fixed = art["inputs"], man["fixed_inputs"]
    assert inp["private_delivery_commit"] == fixed["private_delivery_commit"]
    assert inp["source_revision"] == fixed["source_revision"]
    assert inp["astra_contract_revision"] == fixed["astra_contract_revision"]
    assert inp["exclusion_sha256"] == fixed["p2_060_exclusion_sha256"]
    assert inp["producer_revision"] == man["producer"]["revision"]
    assert inp["producer_git_blob"] == man["producer"]["git_blob"]
    assert inp["producer_sha256"] == man["producer"]["sha256"]


def test_no_private_row_content_in_the_public_artifact():
    text = ARTIFACT.read_text(encoding="utf-8")
    for token in ("stock_id", "2016-", "2017-", "2018-", "2019-", "2020-", "2021-"):
        assert token not in text, token


# --- 真實掃描 / 上游攔截率回歸測試 -------------------------------------------

@pytest.mark.skipif(
    not (os.environ.get("AQ_SOURCE_ROOT") and os.environ.get("AQ_PRODUCER")),
    reason="frozen source / producer not available",
)
def test_real_scan_reproduces_zero_and_upstream_still_catches_everything(art):
    import numpy as np
    import pandas as pd

    spec = importlib.util.spec_from_file_location("aq_producer", os.environ["AQ_PRODUCER"])
    producer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(producer)

    excluded = set(
        pd.read_csv(ROOT / "docs" / "SOURCE_CA_PIT_EXCLUSIONS.csv", dtype={"ticker": str})["ticker"]
    )
    panel = producer.add_c_states(
        producer.add_universe(producer.load_panel(Path(os.environ["AQ_SOURCE_ROOT"]), excluded))
    )
    assert int(panel["all_liquid"].sum()) == ORIGINAL_ROW_COUNT
    assert panel.loc[panel["all_liquid"], "stock_id"].nunique() == 1394

    o, h, l, c = panel["open"], panel["max"], panel["min"], panel["close"]
    checks = {
        "high_lt_low": h.lt(l),
        "high_lt_max_open_close": h.lt(np.maximum(o, c)),
        "low_gt_min_open_close": l.gt(np.minimum(o, c)),
        "nonpositive_ohlc": o.le(0) | h.le(0) | l.le(0) | c.le(0),
        "null_ohlc": o.isna() | h.isna() | l.isna() | c.isna(),
    }
    checks = {k: v.fillna(False) for k, v in checks.items()}
    any_bad = np.logical_or.reduce([v.values for v in checks.values()])

    r = art["result"]
    assert int(checks["high_lt_low"].sum()) == 0
    assert int(any_bad.sum()) == r["any_violation_whole_panel"]
    for name, series in checks.items():
        assert int(series.sum()) == r["violations_by_type_whole_panel"][name], name

    # 這兩行是回歸閘門：上游 flag 一旦放水就會紅。
    assert int((any_bad & panel["valid_ohlc"].values).sum()) == 0
    assert int((any_bad & panel["all_liquid"].values).sum()) == 0
