#!/usr/bin/env python3
"""AQ-EXP-MERGE-PREP-001 — E1 證據線合併後的回歸檢查。

把 PR #8 / #9 / #10 / #11 合併之後，哪些數字必須仍然為真，寫成可執行的斷言。
輸出 PASS / FAIL / SKIP 表；有任何 FAIL 時回傳碼 1。

三層，各自需要的輸入不同：

  L1 公開層   只讀 repo 內的聚合 artifact，無需任何私有資料。
  L2 私有逐列 需要 AQ_COVERAGE_ROWS 指向凍結的私有證據 parquet。
  L3 來源重建 另需 AQ_SOURCE_ROOT 與 AQ_PRODUCER，重跑 producer 函式。

缺輸入的層一律標 SKIP 並寫明缺什麼，不會偽裝成通過。

用法：

    python3 scripts/merge_postcheck.py
    AQ_COVERAGE_ROWS=/path/rows.parquet python3 scripts/merge_postcheck.py
    AQ_COVERAGE_ROWS=... AQ_SOURCE_ROOT=/path/data AQ_PRODUCER=/path/producer.py \
        python3 scripts/merge_postcheck.py --strict

--strict：artifact 不存在時判 FAIL 而非 SKIP。合併完成後請用這個。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MANIFEST = ROOT / "out" / "aq_exp_data_001_r2_manifest.json"
ATR = ROOT / "out" / "aq_exp_atr_001_warmup_correction.json"
GEOM = ROOT / "out" / "aq_exp_geom_001_ohlc_geometry.json"
SURV = ROOT / "out" / "survivorship_e1_universe_contact.json"

# 合併後必須仍為真的數字。改這裡等於改契約，不要順手改。
UNIVERSE_ROWS = 458315
UNIVERSE_STOCKS = 1394
ALL_FOUR = 428102
ATR14_C_V1 = 399
LOW20_C_V1 = 502
ATR14_AFFECTED = 17
ATR14_NUMERIC_AFTER = 457933
ATR14_LIMITED_AFTER = 437435
ATR14_C_AFTER = 382
GEOM_VIOLATIONS_IN_UNIVERSE = 0
SURV_HOLDING_WINDOW_DAYS = 410
HOLDING_PERIOD_DAYS = 60
MANIFEST_PERIOD_END = "2021-12-31"
UNIVERSE_LAST_ROW_DATE = "2021-12-30"

results: list[tuple[str, str, str, str]] = []


def record(layer: str, name: str, status: str, detail: str = "") -> None:
    results.append((layer, name, status, detail))


def check(layer: str, name: str, actual, expected) -> None:
    ok = actual == expected
    record(layer, name, "PASS" if ok else "FAIL",
           "" if ok else f"expected {expected!r}, got {actual!r}")


def load(path: Path, layer: str, strict: bool):
    if not path.exists():
        record(layer, f"artifact {path.relative_to(ROOT)}",
               "FAIL" if strict else "SKIP",
               "not present (expected before the merge; use --strict after it)")
        return None
    return json.loads(path.read_text(encoding="utf-8"))


# --- L1 公開層 --------------------------------------------------------------

def layer1(strict: bool) -> None:
    L = "L1"
    man = load(MANIFEST, L, strict)
    if man:
        check(L, "manifest period_end 未被改動",
              man["denominator"]["period_end"], MANIFEST_PERIOD_END)
        check(L, "manifest 母體列數", man["denominator"]["row_count"], UNIVERSE_ROWS)
        check(L, "manifest 母體檔數", man["denominator"]["unique_stocks"], UNIVERSE_STOCKS)
        f = man["findings"]["atr14_min_bars"]
        check(L, "manifest ATR14 real_feature_delta", f.get("real_feature_delta"), ATR14_AFFECTED)
        check(L, "manifest ATR14 四項交集 delta",
              f.get("isolated_warmup_change_all_four_delta"), 0)

    atr = load(ATR, L, strict)
    if atr:
        r, blk = atr["result"], atr["atr14_feature_aggregate"]
        check(L, "ATR 受影響筆數為確數", r["real_affected_rows"], ATR14_AFFECTED)
        check(L, "ATR is_exact", r["is_exact"], True)
        check(L, "ATR before issue_C", blk["before"]["issue_C_days"], ATR14_C_V1)
        check(L, "ATR after numeric_computable", blk["after"]["numeric_computable"], ATR14_NUMERIC_AFTER)
        check(L, "ATR after limited", blk["after"]["limited_exploration_eligible"], ATR14_LIMITED_AFTER)
        check(L, "ATR after issue_C", blk["after"]["issue_C_days"], ATR14_C_AFTER)
        b = atr["baseline_level_unchanged"]
        check(L, "ATR 後四項交集不變", b["all_four_numeric_computable_after"], ALL_FOUR)
        check(L, "ATR 四項交集 delta", b["all_four_delta"], 0)
        check(L, "ATR 母體列數", b["original_row_count"], UNIVERSE_ROWS)

    geom = load(GEOM, L, strict)
    if geom:
        r = geom["result"]
        check(L, "幾何違反在母體內", r["real_violating_rows_in_universe"], GEOM_VIOLATIONS_IN_UNIVERSE)
        check(L, "幾何違反通過上游 flag 的列數", r["violations_passing_source_valid_ohlc"], 0)
        check(L, "high<low 全 panel", r["high_lt_low_rows_anywhere"], 0)
        imp = geom["feature_aggregate_impact"]
        check(L, "幾何修正後四項交集", imp["all_four_numeric_computable_after"], ALL_FOUR)
        check(L, "幾何修正 delta", imp["all_four_delta"], 0)
        per = imp["per_feature"]
        check(L, "GEOM 記錄的 ATR14 v1 issue_C", per["ATR14"]["before"]["issue_C_days"], ATR14_C_V1)
        check(L, "GEOM 記錄的 LOW20 v1 issue_C", per["LOW20"]["before"]["issue_C_days"], LOW20_C_V1)
        check(L, "GEOM 記錄的 MA120 numeric = 四項交集",
              per["MA120"]["before"]["numeric_computable"], ALL_FOUR)

    surv = load(SURV, L, strict)
    if surv:
        check(L, "倖存者 母體列數", surv["universe_rows"], UNIVERSE_ROWS)
        check(L, "倖存者 母體檔數", surv["universe_stocks"], UNIVERSE_STOCKS)
        check(L, "倖存者 持有期窗長", surv["holding_period_days"], HOLDING_PERIOD_DAYS)
        check(L, "倖存者 持有期窗內股票日",
              surv["days_within_holding_period_of_last_raw"], SURV_HOLDING_WINDOW_DAYS)
        check(L, "倖存者 母體實際最後一列", surv["e1_end_observed"], UNIVERSE_LAST_ROW_DATE)
        check(L, "倖存者 記錄的 manifest 期末", surv["manifest_period_end"], MANIFEST_PERIOD_END)

    # 跨 artifact 一致性：同一個母體不得在不同檔案裡長得不一樣。
    if atr and geom and surv:
        seen = {
            "ATR": atr["baseline_level_unchanged"]["original_row_count"],
            "GEOM": geom["feature_aggregate_impact"]["per_feature"]["MA120"]["before"]["stock_days"],
            "SURV": surv["universe_rows"],
        }
        check("L1", "三份 artifact 的母體列數一致", len(set(seen.values())), 1)
    if atr and geom:
        check("L1", "ATR 與 GEOM 記錄的 ATR14 v1 issue_C 一致",
              atr["atr14_feature_aggregate"]["before"]["issue_C_days"]
              == geom["feature_aggregate_impact"]["per_feature"]["ATR14"]["before"]["issue_C_days"],
              True)


# --- L2 私有逐列 ------------------------------------------------------------

def layer2():
    L = "L2"
    rows_path = os.environ.get("AQ_COVERAGE_ROWS")
    if not rows_path:
        record(L, "私有逐列核對", "SKIP", "AQ_COVERAGE_ROWS 未設定")
        return None
    import pandas as pd

    f = pd.read_parquet(rows_path)
    check(L, "母體列數", len(f), UNIVERSE_ROWS)
    check(L, "母體檔數", f["stock_id"].astype(str).nunique(), UNIVERSE_STOCKS)
    check(L, "ATR14 C rows (v1)", int(f["atr14_issue_c"].sum()), ATR14_C_V1)
    check(L, "LOW20 C rows (v1)", int(f["low20_issue_c"].sum()), LOW20_C_V1)
    check(L, "四項交集 (v1)", int(f["baseline_all_four_numeric_computable"].sum()), ALL_FOUR)
    return f


# --- L3 來源重建 ------------------------------------------------------------

def layer3(frozen):
    L = "L3"
    src, prod_path = os.environ.get("AQ_SOURCE_ROOT"), os.environ.get("AQ_PRODUCER")
    if not (src and prod_path):
        record(L, "來源重建核對", "SKIP", "AQ_SOURCE_ROOT 或 AQ_PRODUCER 未設定")
        return
    if frozen is None:
        record(L, "來源重建核對", "SKIP", "需要 L2 的私有逐列才能接回")
        return
    import numpy as np
    import pandas as pd

    spec = importlib.util.spec_from_file_location("aq_producer", prod_path)
    producer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(producer)
    excluded = set(
        pd.read_csv(ROOT / "docs" / "SOURCE_CA_PIT_EXCLUSIONS.csv", dtype={"ticker": str})["ticker"]
    )
    panel = producer.add_c_states(
        producer.add_universe(producer.load_panel(Path(src), excluded))
    )
    members = panel[panel["all_liquid"]]
    check(L, "重建母體列數", len(members), UNIVERSE_ROWS)
    check(L, "重建母體檔數", members["stock_id"].nunique(), UNIVERSE_STOCKS)

    # 幾何：母體內 0 列，且沒有任何壞列通過上游 flag。
    o, h, l, c = panel["open"], panel["max"], panel["min"], panel["close"]
    bad = (
        h.lt(l) | h.lt(np.maximum(o, c)) | l.gt(np.minimum(o, c))
        | o.le(0) | h.le(0) | l.le(0) | c.le(0)
        | o.isna() | h.isna() | l.isna() | c.isna()
    ).fillna(False).values
    check(L, "幾何違反落在母體內", int((bad & panel["all_liquid"].values).sum()),
          GEOM_VIOLATIONS_IN_UNIVERSE)
    check(L, "幾何違反通過 valid_ohlc", int((bad & panel["valid_ohlc"].values).sum()), 0)

    # ATR14 暖機修正：受影響 17 列，修正後三個數字。
    ord_cols = members[["date", "stock_id", "valid_bar_ordinal", "valid_observed_bar"]].copy()
    fz = frozen.copy()
    fz["date"] = pd.to_datetime(fz["date"]).dt.normalize()
    fz["stock_id"] = fz["stock_id"].astype(str)
    j = fz.merge(ord_cols, on=["date", "stock_id"], how="left", validate="one_to_one")
    check(L, "ordinal 接回無缺值", int(j["valid_bar_ordinal"].isna().sum()), 0)
    aff = j["atr14_issue_c"] & j["valid_bar_ordinal"].eq(14) & j["valid_observed_bar"]
    check(L, "ATR14 受影響列數", int(aff.sum()), ATR14_AFFECTED)
    check(L, "受影響列的 LOW20 仍為 C", bool(j.loc[aff, "low20_issue_c"].all()), True)
    after_c = j["atr14_issue_c"] & ~aff
    b = j["atr14_issue_b"].astype(bool)
    check(L, "ATR14 修正後 issue_C", int(after_c.sum()), ATR14_C_AFTER)
    check(L, "ATR14 修正後 numeric", int((~after_c).sum()), ATR14_NUMERIC_AFTER)
    check(L, "ATR14 修正後 limited", int(((~after_c) & (~b)).sum()), ATR14_LIMITED_AFTER)
    four_after = (
        (~after_c) & j["ma120_numeric_computable"]
        & j["n60_numeric_computable"] & j["low20_numeric_computable"]
    )
    check(L, "ATR14 修正後四項交集", int(four_after.sum()), ALL_FOUR)

    # 倖存者：持有期等長窗內 410 股票日。
    scan = ROOT / "scripts" / "survivorship_72_scan.py"
    if not scan.exists():
        record(L, "倖存者 60 日窗", "SKIP", "scripts/survivorship_72_scan.py 尚未合併")
        return
    s_spec = importlib.util.spec_from_file_location("surv_scan", scan)
    surv_mod = importlib.util.module_from_spec(s_spec)
    s_spec.loader.exec_module(surv_mod)
    res, _ = surv_mod.contact(os.environ["AQ_COVERAGE_ROWS"], surv_mod.unmodeled_tickers())
    check(L, "倖存者 持有期窗內股票日",
          res["days_within_holding_period_of_last_raw"], SURV_HOLDING_WINDOW_DAYS)
    check(L, "倖存者 母體列數", res["universe_rows"], UNIVERSE_ROWS)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true",
                    help="artifact 不存在時判 FAIL（合併完成後使用）")
    args = ap.parse_args()

    layer1(args.strict)
    frozen = layer2()
    layer3(frozen)

    w = max(len(n) for _, n, _, _ in results) + 2
    print(f"{'LAYER':<7}{'CHECK':<{w}}{'STATUS':<8}DETAIL")
    print("-" * (7 + w + 8 + 40))
    for layer, name, status, detail in results:
        print(f"{layer:<7}{name:<{w}}{status:<8}{detail}")
    n_pass = sum(1 for r in results if r[2] == "PASS")
    n_fail = sum(1 for r in results if r[2] == "FAIL")
    n_skip = sum(1 for r in results if r[2] == "SKIP")
    print("-" * (7 + w + 8 + 40))
    print(f"PASS {n_pass}  FAIL {n_fail}  SKIP {n_skip}")
    if n_skip and not n_fail:
        print("注意：有 SKIP 項目，本次執行不足以證明合併結果正確。")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
