"""AQ-EXP-ATR-001 — ATR14 暖機修正的受影響筆數。

公開部分只驗聚合檔自洽與正式契約的暖機門檻；
真實逐列核對需要私有交付與固定 source，缺任一項即 skip，不偽裝已執行。
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "out" / "aq_exp_atr_001_warmup_correction.json"
R2_MANIFEST = ROOT / "out" / "aq_exp_data_001_r2_manifest.json"

EXPECTED_AFFECTED = 17
ORIGINAL_ROW_COUNT = 458315
ATR_C_V1 = 399
ALL_FOUR_V1 = 428102

YEARS = ["2016", "2017", "2018", "2019", "2020", "2021"]


@pytest.fixture(scope="module")
def art():
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


def test_result_is_exact_not_a_bound(art):
    r = art["result"]
    assert r["real_affected_rows"] == EXPECTED_AFFECTED
    assert r["is_exact"] is True
    assert art["supersedes_finding"]["previous_upper_bound"] == ATR_C_V1
    assert r["real_affected_rows"] < ATR_C_V1


def test_ordinal_histogram_accounts_for_every_c_row(art):
    hist = art["result"]["atr14_c_rows_by_valid_bar_ordinal"]
    assert sorted(int(k) for k in hist) == list(range(1, 15))
    assert sum(hist.values()) == ATR_C_V1
    # 只有第 14 根那一格會翻轉，其餘仍不足 14 根。
    assert hist["14"] == EXPECTED_AFFECTED
    assert art["result"]["atr14_c_rows_remaining_after_correction"] == ATR_C_V1 - hist["14"]


def test_feature_aggregate_is_internally_consistent(art):
    blk = art["atr14_feature_aggregate"]
    before, after, delta = blk["before"], blk["after"], blk["delta"]
    for key, value in after.items():
        assert value == before[key] + delta.get(key, 0), key
    assert before["stock_days"] == after["stock_days"] == ORIGINAL_ROW_COUNT
    assert before["issue_C_days"] == ATR_C_V1
    assert delta["numeric_computable"] == EXPECTED_AFFECTED
    assert delta["issue_C_days"] == -EXPECTED_AFFECTED
    assert delta["known_affected_days"] == -EXPECTED_AFFECTED
    assert delta["indeterminate_days"] == EXPECTED_AFFECTED
    # numeric 與 C 互補；B 曝光未重跑所以不得變動。
    assert after["numeric_computable"] + after["issue_C_days"] == ORIGINAL_ROW_COUNT
    assert delta.get("issue_B_days", 0) == 0


def test_limited_gain_is_one_short_because_of_an_existing_b_exposure(art):
    blk = art["atr14_feature_aggregate"]
    r = art["result"]
    assert r["affected_with_atr14_issue_b"] == 1
    assert blk["delta"]["limited_exploration_eligible"] == EXPECTED_AFFECTED - 1
    # 該筆 b_known 為 False，故由 KNOWN_AFFECTED 轉 INDETERMINATE 而非留在 KNOWN_AFFECTED。
    assert r["affected_with_atr14_b_known"] == 0
    assert blk["delta"]["dominant_B"] == 1
    assert blk["delta"]["dominant_A"] == EXPECTED_AFFECTED - 1


def test_yearly_blocks_sum_to_the_feature_total(art):
    yearly = art["atr14_yearly_aggregate"]
    assert sorted(yearly) == YEARS
    total = art["atr14_feature_aggregate"]
    for side in ("before", "after"):
        for key in total[side]:
            assert sum(yearly[y][side][key] for y in YEARS) == total[side][key], (side, key)
    by_year = art["result"]["affected_by_year"]
    assert sum(by_year.values()) == EXPECTED_AFFECTED
    for y in YEARS:
        assert -yearly[y]["delta"].get("issue_C_days", 0) == by_year.get(y, 0)


def test_four_way_intersection_delta_is_zero(art):
    b = art["baseline_level_unchanged"]
    assert b["all_four_numeric_computable_before"] == ALL_FOUR_V1
    assert b["all_four_numeric_computable_after"] == ALL_FOUR_V1
    assert b["all_four_delta"] == 0
    assert b["agrees_with_pr8_argument"] is True
    assert b["baseline_yearly_table_unchanged"] is True
    assert b["original_row_count"] == ORIGINAL_ROW_COUNT


def test_gate_and_scope_are_not_relaxed(art):
    assert art["execution_authorized"] is False
    assert art["formal_research_gate"] == "BLOCKED_UNCONDITIONALLY"
    assert art["scope"] == "SOURCE_EVIDENCE"
    assert art["method"]["features_touched"] == ["ATR14"]
    assert art["method"]["b_exposure_recomputed"] is False
    assert art["method"]["original_population_recomputed"] is False


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
    found = man["findings"]["atr14_min_bars"]
    assert found["producer"] == 15 and found["formal"] == 14
    assert found["real_feature_delta"] == EXPECTED_AFFECTED
    assert found["isolated_warmup_change_all_four_delta"] == 0


def test_no_private_row_content_in_the_public_artifact():
    text = ARTIFACT.read_text(encoding="utf-8")
    banned = ("stock_id", "2016-", "2017-", "2018-", "2019-", "2020-", "2021-")
    for token in banned:
        assert token not in text, token


def test_formal_contract_needs_only_fourteen_valid_bars():
    from astraquant.research.baseline_60d_exit_state import ATR_PERIOD

    assert ATR_PERIOD == 14
    # 第一根 TR = high - low，之後 13 根各 2 → 14 根即可給值。
    first_tr = 103 - 97
    assert pytest.approx((first_tr + 13 * 2) / 14) == 32 / 14


# --- 真實逐列核對（需要私有交付與固定 source）---------------------------------

def _load_producer(path: str):
    spec = importlib.util.spec_from_file_location("aq_producer", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.skipif(
    not (os.environ.get("AQ_COVERAGE_ROWS")
         and os.environ.get("AQ_SOURCE_ROOT")
         and os.environ.get("AQ_PRODUCER")),
    reason="private row table / frozen source / producer not available",
)
def test_real_affected_rows_reproduce(art):
    import pandas as pd

    producer = _load_producer(os.environ["AQ_PRODUCER"])
    excluded = set(
        pd.read_csv(ROOT / "docs" / "SOURCE_CA_PIT_EXCLUSIONS.csv", dtype={"ticker": str})["ticker"]
    )
    panel = producer.add_c_states(
        producer.add_universe(producer.load_panel(Path(os.environ["AQ_SOURCE_ROOT"]), excluded))
    )
    members = panel[panel["all_liquid"]][
        ["date", "stock_id", "valid_bar_ordinal", "valid_observed_bar"]
    ].copy()
    assert len(members) == ORIGINAL_ROW_COUNT
    assert members["stock_id"].nunique() == 1394

    rows = pd.read_parquet(os.environ["AQ_COVERAGE_ROWS"])
    rows["date"] = pd.to_datetime(rows["date"]).dt.normalize()
    rows["stock_id"] = rows["stock_id"].astype(str)
    joined = rows.merge(members, on=["date", "stock_id"], how="left", validate="one_to_one")
    assert joined["valid_bar_ordinal"].notna().all()

    # 重建的 C 判定必須與凍結交付逐列相同，否則重建不可信。
    assert (joined["valid_bar_ordinal"].lt(15).values == joined["atr14_issue_c"].values).all()
    assert (joined["valid_bar_ordinal"].le(20).values == joined["low20_issue_c"].values).all()
    assert int(joined["atr14_issue_c"].sum()) == ATR_C_V1

    affected = (
        joined["atr14_issue_c"]
        & joined["valid_bar_ordinal"].eq(14)
        & joined["valid_observed_bar"]
    )
    assert int(affected.sum()) == EXPECTED_AFFECTED
    # 四項交集增量必為 0：這些列的 LOW20 仍不可算。
    assert bool(joined.loc[affected, "low20_issue_c"].all())
    by_year = joined.loc[affected, "date"].dt.year.value_counts().to_dict()
    assert {str(k): int(v) for k, v in by_year.items()} == art["result"]["affected_by_year"]
