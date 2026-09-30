#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

from astraquant.research.ca_adjustment_audit import (
    BOUNDARY_BAND,
    PRICE_REBUILD_ATOL,
    VALUE_ATOL,
    VALUE_RTOL,
    current_price_feature_frame,
    future_factor_for_rows,
    normalize_dividend_events,
    online_asof_price_features,
    rebuild_final_adjusted_close,
    synthetic_uniform_scale_case,
    universe_masks,
)
from pit_feature_matrix_layer1 import dictionary_frame

SOURCE_ROOT = Path(os.environ["SOURCE_ROOT"]).resolve()
SOURCE_REVISION = os.environ.get("SOURCE_REVISION", "").strip()
EXPECTED_SOURCE_REVISION = "fb8b042b46dc38838d103544ca17da10286c7bfe"
E1_START = pd.Timestamp("2016-01-04")
E1_END = pd.Timestamp("2021-12-31")
WARMUP_START = pd.Timestamp("2015-01-01")
EXCLUSIONS = Path("docs/SOURCE_CA_PIT_EXCLUSIONS.csv")
EXCLUSION_SHA = "379d58f6a8aa06b1e020d56911930f4bc01861d3eeca109613d9e5b1e490d134"
OUT = Path("out")
REPORT = Path("docs/CA_ADJUSTMENT_INVARIANCE_AUDIT.md")

def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def load_years(subdir, prefix, columns):
    parts = []
    for year in range(2015, 2022):
        p = SOURCE_ROOT / subdir / f"{prefix}_{year}.parquet"
        if not p.exists():
            raise SystemExit(f"BLOCKED: missing {p}")
        x = pd.read_parquet(p, columns=columns)
        x["date"] = pd.to_datetime(x["date"], errors="coerce").dt.normalize()
        x["stock_id"] = x["stock_id"].astype(str)
        x = x[x["date"].between(WARMUP_START, E1_END, inclusive="both")]
        parts.append(x)
    out = pd.concat(parts, ignore_index=True)
    if out.duplicated(["date", "stock_id"]).any():
        raise SystemExit(f"BLOCKED: duplicate {subdir}/{prefix} keys")
    return out.sort_values(["stock_id", "date"], kind="stable").reset_index(drop=True)

def exclusions():
    if sha256(EXCLUSIONS) != EXCLUSION_SHA:
        raise SystemExit("BLOCKED: P2-060 exclusion SHA changed")
    return set(pd.read_csv(EXCLUSIONS, dtype={"ticker": str})["ticker"].astype(str))

def yearly_feature(f):
    e = f[f["date"].between(E1_START, E1_END, inclusive="both")].copy()
    e["year"] = e["date"].dt.year
    rows = []
    for year, g in e.groupby("year", sort=True):
        ma = g["ma120_comparable"].fillna(False)
        n60 = g["n60_comparable"].fillna(False)
        rows.append({
            "year": int(year),
            "feature_source_rows": len(g),
            "feature_unique_stocks": g["stock_id"].nunique(),
            "future_factor_not_one_rows": int((~np.isclose(g["future_factor"], 1.0, rtol=0, atol=1e-15)).sum()),
            "ma120_comparable": int(ma.sum()),
            "ma120_value_diff_factor_only": int((g["ma120_value_diff"] & ma).sum()),
            "ma120_gate_flips_factor_only": int((g["ma120_gate_flip"] & ma).sum()),
            "ma120_near_boundary": int((g["ma120_near_boundary"] & ma).sum()),
            "n60_comparable": int(n60.sum()),
            "n60_signal_flips_factor_only": int((g["n60_flip"] & n60).sum()),
            "n60_near_boundary": int((g["n60_near_boundary"] & n60).sum()),
        })
    return pd.DataFrame(rows)

def online_compare(online, current):
    cols = ["date","stock_id","close_to_ma120_current","ma120_gate_current","n60_current","n60_comparable"]
    x = online.merge(current[cols], on=["date","stock_id"], how="left", validate="one_to_one")
    x = x[x["date"].between(E1_START, E1_END, inclusive="both")].copy()
    x["year"] = x["date"].dt.year
    x["online_ma_comparable"] = x["close_to_ma120_online_asof"].notna() & x["close_to_ma120_current"].notna()
    x["online_ma_diff"] = ~np.isclose(x["close_to_ma120_online_asof"], x["close_to_ma120_current"], rtol=VALUE_RTOL, atol=VALUE_ATOL, equal_nan=True)
    x["online_ma_gate_flip"] = x["ma120_gate_online_asof"] != x["ma120_gate_current"]
    x["online_n_comparable"] = x["n60_comparable"].fillna(False) & ~x["raw_close_missing"].fillna(True)
    x["online_n_flip"] = x["n60_online_asof"] != x["n60_current"]
    rows = []
    for year, g in x.groupby("year", sort=True):
        ma = g["online_ma_comparable"]
        ns = g["online_n_comparable"]
        rows.append({
            "year": int(year),
            "online_ma120_comparable": int(ma.sum()),
            "online_ma120_value_diff_vs_final": int((g["online_ma_diff"] & ma).sum()),
            "online_ma120_gate_flips_vs_final": int((g["online_ma_gate_flip"] & ma).sum()),
            "online_n60_comparable": int(ns.sum()),
            "online_n60_signal_flips_vs_final": int((g["online_n_flip"] & ns).sum()),
            "raw_close_missing_on_adjusted_rows": int(g["raw_close_missing"].sum()),
        })
    return pd.DataFrame(rows), x

def yearly_universe(u):
    e = u[u["date"].between(E1_START, E1_END, inclusive="both")].copy()
    e["year"] = e["date"].dt.year
    rows = []
    for year, g in e.groupby("year", sort=True):
        comparable = ~g["raw_close_missing"] & g["adjusted_close"].notna()
        add_gate = comparable & g["raw_close_gate"] & ~g["adjusted_close_gate"] & g["fixed_other_qualifiers"]
        rem_gate = comparable & g["adjusted_close_gate"] & ~g["raw_close_gate"] & g["fixed_other_qualifiers"]
        base_add = g["raw_base_pass"] & ~g["adjusted_base_pass"]
        base_rem = g["adjusted_base_pass"] & ~g["raw_base_pass"]
        final_add = g["raw_counts"] & ~g["adjusted_counts"]
        final_rem = g["adjusted_counts"] & ~g["raw_counts"]
        fd = final_add | final_rem
        rows.append({
            "year": int(year),
            "universe_source_rows": len(g),
            "raw_close_missing": int(g["raw_close_missing"].sum()),
            "adjusted_close_missing": int(g["adjusted_close"].isna().sum()),
            "close_gate_raw_add_vs_adjusted": int(add_gate.sum()),
            "close_gate_raw_remove_vs_adjusted": int(rem_gate.sum()),
            "close_gate_diff_unique_stocks": int(g.loc[add_gate | rem_gate, "stock_id"].nunique()),
            "base_pass_raw_add_vs_adjusted": int(base_add.sum()),
            "base_pass_raw_remove_vs_adjusted": int(base_rem.sum()),
            "final_universe_raw_add_vs_adjusted": int(final_add.sum()),
            "final_universe_raw_remove_vs_adjusted": int(final_rem.sum()),
            "final_universe_diff_unique_stocks": int(g.loc[fd, "stock_id"].nunique()),
        })
    return pd.DataFrame(rows)

def source_validation(joined, rebuilt):
    x = joined.merge(rebuilt, on=["date","stock_id"], how="left", validate="one_to_one")
    rows = []
    for label, col in [("round_once","rebuild_round_once"),("sequential_round4","rebuild_sequential_round4")]:
        for year in ["ALL_E1", 2016, 2017, 2018, 2019, 2020, 2021]:
            g = x[x["date"].between(E1_START,E1_END,inclusive="both")] if year == "ALL_E1" else x[x["date"].dt.year.eq(year)]
            comp = g["adjusted_close"].notna() & g[col].notna()
            diff = (g.loc[comp,"adjusted_close"] - g.loc[comp,col]).abs()
            rows.append({
                "comparison": label, "year": year, "rows": len(g), "comparable": int(comp.sum()),
                "match_within_0_00005": int(diff.le(PRICE_REBUILD_ATOL + 1e-12).sum()),
                "mismatch": int(diff.gt(PRICE_REBUILD_ATOL + 1e-12).sum()),
                "median_abs_diff": float(diff.median()) if len(diff) else np.nan,
                "max_abs_diff": float(diff.max()) if len(diff) else np.nan,
            })
    return pd.DataFrame(rows)

def classify(universe_changed):
    d = dictionary_frame()
    affected_units = {"macd_hist_12_26_9","macd_hist_slope5"}
    universe_derived = {"market_cap_tier","liquidity_tier","volatility_cluster"}
    nonprice = {"volume_ratio_5_20","volume_ratio_20_60","amount_mean20_twd","turnover_value_ratio","volume_dryup_prior5_20","industry","market_cap_twd"}
    rows = []
    for r in d.itertuples(index=False):
        col = str(r.column)
        if r.status == "BLOCKED_DATA":
            cls, why = "INSUFFICIENT_EVIDENCE", "source itself BLOCKED_DATA"
        elif r.table == "market_context":
            cls, why = "PROVEN_INVARIANT_TO_SPECIFIED_STOCK_ADJUSTMENT", "separate TAIEX TRI source"
        elif col in affected_units:
            cls, why = "PROVEN_AFFECTED_VALUE", "price-unit formula scales with adjusted price"
        elif col in universe_derived or col.startswith(("rs_industry_","industry_rs_market_","industry_strength_rank_")):
            cls, why = ("PROVEN_AFFECTED_VIA_UNIVERSE" if universe_changed else "UNIVERSE_DEPENDENT"), "eligible cross-section can change"
        elif r.status == "CONTROL" or col in nonprice:
            cls, why = "PROVEN_INVARIANT_TO_SPECIFIED_STOCK_ADJUSTMENT", "does not consume adjusted OHLC value"
        else:
            cls, why = "PROVEN_INVARIANT_TO_COMMON_POSITIVE_SCALE", "dimensionless/order/return formula under full-window common positive scale"
        rows.append({
            "item_id": r.item_id, "column": col, "parameter_version": r.parameter_version, "table": r.table,
            "classification": cls, "proof_scope": why,
            "persisted_row_membership_sensitive": r.table == "stock_features",
            "percentile_output_membership_sensitive": bool(r.table == "stock_features" and r.cross_section_rank and universe_changed),
            "note": "value classification only; publication-time PIT not established",
        })
    return pd.DataFrame(rows)

def md(df):
    if df.empty:
        return "無"
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"]*len(cols)) + "|"]
    for row in df.itertuples(index=False, name=None):
        vals = [("" if pd.isna(v) else (f"{v:.8g}" if isinstance(v,float) else str(v))) for v in row]
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)

def main():
    if SOURCE_REVISION != EXPECTED_SOURCE_REVISION:
        raise SystemExit(f"BLOCKED: source revision {SOURCE_REVISION}")
    OUT.mkdir(exist_ok=True)

    adj = load_years("adj","prices_adj",["date","stock_id","close","Trading_money"]).rename(columns={"close":"adjusted_close"})
    raw = load_years("raw","prices_raw",["date","stock_id","close","Trading_money"]).rename(columns={"close":"raw_close","Trading_money":"raw_Trading_money"})
    events_raw = pd.read_parquet(SOURCE_ROOT / "adj" / "dividend_events.parquet")
    events = normalize_dividend_events(events_raw)

    fixed = adj.merge(raw[["date","stock_id","raw_close"]], on=["date","stock_id"], how="left", validate="one_to_one")
    f_in = fixed[["date","stock_id","adjusted_close"]].rename(columns={"adjusted_close":"close"})
    ff = future_factor_for_rows(f_in, events)
    factor = current_price_feature_frame(f_in, future_factor=ff)
    yf = yearly_feature(factor)

    online = online_asof_price_features(fixed[["date","stock_id","raw_close"]], events)
    yo, online_rows = online_compare(online, factor)
    rebuilt = rebuild_final_adjusted_close(fixed[["date","stock_id","raw_close"]], events)
    sv = source_validation(fixed, rebuilt)

    # Universe starts from the union of pre-filter source rows, not feature artifact rows.
    universe_source = adj.merge(raw[["date","stock_id","raw_close","raw_Trading_money"]], on=["date","stock_id"], how="outer", validate="one_to_one")
    universe_source["Trading_money"] = universe_source["Trading_money"].combine_first(universe_source["raw_Trading_money"])
    trad = pd.read_parquet(SOURCE_ROOT / "reference" / "tradability.parquet", columns=["date","stock_id","observed_trade","valid_ohlc"])
    trad["date"] = pd.to_datetime(trad["date"], errors="coerce").dt.normalize()
    trad["stock_id"] = trad["stock_id"].astype(str)
    universe_source = universe_source[universe_source["date"].between(E1_START,E1_END,inclusive="both")].merge(trad,on=["date","stock_id"],how="left",validate="one_to_one")
    universe_source["observed_trade"] = universe_source["observed_trade"].fillna(False).astype(bool)
    universe_source["valid_ohlc"] = universe_source["valid_ohlc"].fillna(False).astype(bool)
    u = universe_masks(universe_source, excluded=exclusions())
    yu = yearly_universe(u)
    yearly = yf.merge(yo,on="year",how="outer",validate="one_to_one").merge(yu,on="year",how="outer",validate="one_to_one").sort_values("year")

    final_diff_mask = u["adjusted_counts"] != u["raw_counts"]
    final_diff = int(final_diff_mask.sum())
    final_unique = int(u.loc[final_diff_mask,"stock_id"].nunique())
    classes = classify(final_diff > 0)

    synth = synthetic_uniform_scale_case()
    factor_value_diffs = int(yearly["ma120_value_diff_factor_only"].sum())
    factor_ma_flips = int(yearly["ma120_gate_flips_factor_only"].sum())
    factor_n60_flips = int(yearly["n60_signal_flips_factor_only"].sum())
    if factor_value_diffs or factor_ma_flips or factor_n60_flips:
        raise SystemExit("FAIL: common-factor invariance check flipped MA/N60")
    if synth["ma120_gate_flips"] or synth["n60_flips"] or not synth["absolute_close_threshold_flips"]:
        raise SystemExit("FAIL: synthetic controls")

    examples = []
    def take(kind, frame, mask, cols):
        z = frame.loc[mask,["date","stock_id",*cols]].head(12).copy()
        if len(z):
            z.insert(0,"case_type",kind); examples.append(z)
    take("ONLINE_MA120_GATE_FLIP",online_rows,online_rows["online_ma_gate_flip"] & online_rows["online_ma_comparable"],["close_to_ma120_current","close_to_ma120_online_asof"])
    take("ONLINE_N60_FLIP",online_rows,online_rows["online_n_flip"] & online_rows["online_n_comparable"],["n60_current","n60_online_asof"])
    take("RAW_CLOSE_GATE_ADDS",u,(u["raw_close_gate"] & ~u["adjusted_close_gate"] & u["fixed_other_qualifiers"]),["adjusted_close","raw_close","Trading_money"])
    take("FINAL_UNIVERSE_RAW_ADDS",u,(u["raw_counts"] & ~u["adjusted_counts"]),["adjusted_close","raw_close","Trading_money","adjusted_turnover_pct","raw_turnover_pct"])
    ex = pd.concat(examples,ignore_index=True,sort=False) if examples else pd.DataFrame(columns=["case_type","date","stock_id"])

    vcp_shared = (
        "configs/examples/universes/all_liquid.yaml" in Path("configs/research/vcp_round1_three_segment_v1.yaml").read_text()
        and "_research_panel" in Path("scripts/source_vcp_round1.py").read_text()
        and "adjusted = load_adjusted()" in Path("scripts/source_config_sweep.py").read_text()
    )
    vcp_status = "待影響評估" if vcp_shared and final_diff else "本稽核未觀察到母體翻轉"

    yearly_path = OUT/"ca_adjustment_invariance_audit_yearly.csv"
    source_path = OUT/"ca_adjustment_invariance_source_validation.csv"
    examples_path = OUT/"ca_adjustment_invariance_examples.csv"
    class_path = OUT/"ca_adjustment_invariance_feature_classification.csv"
    manifest_path = OUT/"ca_adjustment_invariance_manifest.json"
    yearly.to_csv(yearly_path,index=False)
    sv.to_csv(source_path,index=False)
    ex.to_csv(examples_path,index=False)
    classes.to_csv(class_path,index=False)

    event_cols = list(map(str,events_raw.columns))
    knowledge_cols = [c for c in event_cols if any(t in c.lower() for t in ("known","announce","publish","release","created","update_time"))]
    lines = [
        "# 公司行動回溯調整的實際影響稽核","",
        "狀態：完成資料、特徵與候選資格一致性稽核，待第 5 項審查。","",
        "本稽核不計算任何策略效果；沒有執行 baseline、Round 2、ML，也沒有重跑 VCP Round 1。","",
        "## 固定來源與算法","",
        f"- source revision：{SOURCE_REVISION}",
        "- build_adj：event ratio=after_price/before_price；歷史日乘其後事件正倍率；OHLC round(4)。",
        "- daily_update_adj：事件日先回寫歷史 OHLC，再 append 當日 RAW；Trading_Volume、Trading_money 不乘因子。",
        f"- 有效 date-stock event rows：{len(events):,}；E1 結束後 event rows：{int(events['date'].gt(E1_END).sum()):,}。",
        f"- knowledge-time 欄位候選：{knowledge_cols if knowledge_cols else '無'}；event.date>T 只代表晚於 T 生效，不等於 T 時未知。","",
        "## 方法與容差","",
        f"- ratio rtol={VALUE_RTOL}, atol={VALUE_ATOL}; boundary band={BOUNDARY_BAND}; 布林翻轉不用容差。",
        f"- RAW 到 stored adjusted 重建價格 tolerance={PRICE_REBUILD_ATOL} TWD。",
        "- factor-only 只移除 T 後事件的共同倍率；online RAW+event 是用目前 frozen 檔倒推的 counterfactual，不冒稱 contemporaneous snapshot。","",
        f"- 合成：MA120 flips={synth['ma120_gate_flips']}；N60 flips={synth['n60_flips']}；close>=10 flip={synth['absolute_close_threshold_flips']}。","",
        "## E1 逐年結果","",md(yearly),"",
        "factor-only 欄回答共同倍率本身；online 欄同時可能含 rounding、RAW 修訂、缺列等差異，不能直接歸因於未來事件。","",
        "## 來源重建一致性","",md(sv),"",
        "## all_liquid 母體","",
        "- UniverseCompiler 的 min_close_twd=10 讀 caller panel close；feature build 與 VCP Round 1 research panel 都傳 adjusted close。",
        "- RAW close>=10 僅為診斷對照；P2-060、ticker regex、observed_trade、valid_ohlc、Trading_money、top25% 固定。",
        f"- E1 final all_liquid stock-day 差異：{final_diff:,}；涉及 {final_unique:,} 檔。","",
        "## 特徵影響分類","",md(classes.groupby("classification",as_index=False).size().rename(columns={"size":"rows"})),"",
        "- MA ratio、相對高低、returns/vol、ATR/close、Bollinger ratio、RSI、KD、CCI、Williams 等在完整回看窗共同正倍率下原值不變。",
        "- MACD histogram/slope 是 price-unit，原值會縮放。",
        "- persisted stock rows、percentile、tier 與 industry cross-section 仍可能因 eligible universe 改變而受影響。",
        "- 值不變只解除這一項調整依賴，不代表發布時間或其他 PIT 條件通過。","",
        "## 差異案例","",md(ex.head(30)),"",
        "## VCP Round 1 依賴","",
        f"- shared all_liquid path={vcp_shared}；狀態={vcp_status}。",
        "- 原結果保留、不重跑、不宣告績效失效；若母體翻轉，後續比較不得稱為乾淨共同基準。","",
        "## 最小修正方案（提案，不執行）","",
        "- 保留：已證明尺度不變的公式與測試、MA120 >=0 evaluator、hydration/checksum/null contract、既有 Round 1 結果檔。",
        "- 另建版本：若 owner 核定 PIT-safe absolute-price universe，依 eligible membership 的 feature rows/percentile/tier 需新版本重建；不必推倒尺度不變公式。",
        "- MACD price-unit 原值需在核定 causal coordinate 另驗。",
        "- 尚缺：完整 E1 receipt/publish/known-time；目前 frozen RAW 不是 contemporaneous snapshot；其他 EOD/RAW/TRI/industry cutoff evidence 維持原 gate。","",
        "## 停止點","",
        "不改正式母體、不重建正式 feature artifact、不修改或重跑策略結果；停在第 5 項公司行動影響稽核驗收。"
    ]
    REPORT.write_text("\n".join(lines)+"\n",encoding="utf-8")

    manifest = {
        "audit_version":"ca_adjustment_invariance_audit_v1","source_revision":SOURCE_REVISION,
        "epoch":"E1","e1_period":[str(E1_START.date()),str(E1_END.date())],
        "no_effect_metrics":True,"strategy_runs_executed":[],
        "value_tolerance":{"rtol":VALUE_RTOL,"atol":VALUE_ATOL},"boundary_band":BOUNDARY_BAND,
        "price_rebuild_atol":PRICE_REBUILD_ATOL,"knowledge_time_proven":False,
        "future_event_definition":"event.date > decision_date T",
        "factor_only_results":{"ma120_value_diffs":factor_value_diffs,"ma120_gate_flips":factor_ma_flips,"n60_signal_flips":factor_n60_flips},
        "universe_results":{"final_stock_day_differences":final_diff,"unique_stocks_with_final_difference":final_unique},
        "vcp_round1_shared_universe_path":vcp_shared,"vcp_round1_status":vcp_status,
        "synthetic_control":synth,"outputs":{}
    }
    for p in [yearly_path,source_path,examples_path,class_path,REPORT]:
        manifest["outputs"][str(p)]={"sha256":sha256(p),"size_bytes":p.stat().st_size}
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

if __name__ == "__main__":
    main()
