#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pandas as pd
import yaml

from astraquant.research.benchmark import load_finmind_total_return_index
from astraquant.research.config_io import load_universe_config
from astraquant.research.technical_components import column_threshold
from astraquant.research.strategy_config import ComponentSpec
from astraquant.research.universe_engine import UniverseCompiler, UniverseContext


ROOT = Path(".").resolve()
CONFIG_PATH = Path(os.environ.get(
    "FEATURE_REVIEW_CONFIG",
    "configs/quality/pit_feature_matrix_layer1_v1_review1.yaml",
))
SOURCE_ROOT = Path(os.environ.get(
    "SOURCE_ROOT",
    "source_runtime/minervini_picks/data",
)).resolve()
EXPECTED_EXCLUSION_SHA = "379d58f6a8aa06b1e020d56911930f4bc01861d3eeca109613d9e5b1e490d134"
EXCLUSIONS_PATH = Path("docs/SOURCE_CA_PIT_EXCLUSIONS.csv")


SOURCE_EVIDENCE = {
    "adjusted_eod": {
        "status": "UNKNOWN",
        "evidence_type": "DATA_CONTRACT_PLUS_SCHEMA_GAP",
        "timestamp_field": "NONE",
        "basis": (
            "DATA_CONTRACT permits adjusted research series, but canonical parquet "
            "inventory observes no available_at/known_date field for prices_adj. "
            "Session date is not an actual provider publication timestamp."
        ),
    },
    "tradability": {
        "status": "UNKNOWN",
        "evidence_type": "SCHEMA_GAP",
        "timestamp_field": "NONE",
        "basis": (
            "tradability has session date and source provenance but no observed "
            "available_at timestamp; same-session decision-time availability is unproven."
        ),
    },
    "market_value": {
        "status": "UNKNOWN",
        "evidence_type": "SCHEMA_GAP",
        "timestamp_field": "NONE",
        "basis": (
            "market_value parquet has date only and no available_at/known_date field. "
            "No one-day delay is assumed."
        ),
    },
    "industry_pit": {
        "status": "UNKNOWN",
        "evidence_type": "SOURCE_AVAILABLE_DATE_DATE_ONLY",
        "timestamp_field": "valid_from derived from source available_date",
        "basis": (
            "industry PIT is causally built from official MOPS snapshot available_date "
            "or exact reclassification effective_date, but time-of-day is absent; "
            "date-level causality passes while exact AFTER_SESSION_CLOSE usability "
            "on the same date remains unproven."
        ),
    },
    "index_tri": {
        "status": "UNKNOWN",
        "evidence_type": "SCHEMA_GAP",
        "timestamp_field": "NONE",
        "basis": (
            "FinMind TaiwanStockTotalReturnIndex file records date/value but no "
            "available_at timestamp; exact same-session post-close publication is unproven."
        ),
    },
    "random_control": {
        "status": "PASS",
        "evidence_type": "DETERMINISTIC_INTERNAL",
        "timestamp_field": "not applicable",
        "basis": (
            "Value is a deterministic function of date, stock_id, feature_id and fixed seed; "
            "no external future information is consumed."
        ),
    },
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def combine_status(statuses: list[str]) -> str:
    clean = [str(x).upper() for x in statuses]
    if any(x == "FAIL" for x in clean):
        return "FAIL"
    if any(x == "UNKNOWN" for x in clean):
        return "UNKNOWN"
    if clean and all(x == "PASS" for x in clean):
        return "PASS"
    return "UNKNOWN"


def stable_stratified_sample(
    frame: pd.DataFrame,
    *,
    year_col: str,
    per_year: int,
    seed: int,
    id_cols: list[str],
    years: list[int],
) -> pd.DataFrame:
    if per_year <= 0:
        raise ValueError("per_year must be positive")
    pieces = []
    for year in years:
        g = frame[frame[year_col].astype(int).eq(int(year))].copy()
        if g.empty:
            raise ValueError(f"sampling stratum is empty: {year}")
        key = g[id_cols].astype(str).agg("|".join, axis=1)
        salted = key + f"|seed={int(seed)}|year={int(year)}"
        g["_sample_order"] = pd.util.hash_pandas_object(
            salted, index=False, hash_key="0123456789123456"
        ).astype("uint64")
        take = min(per_year, len(g))
        pieces.append(
            g.sort_values(["_sample_order", *id_cols], kind="stable")
            .head(take)
            .drop(columns=["_sample_order"])
        )
    out = pd.concat(pieces, ignore_index=True)
    observed = sorted(out[year_col].astype(int).unique().tolist())
    if observed != sorted(int(x) for x in years):
        raise AssertionError(f"stratified sample lost years: {observed}")
    return out


def feature_dependencies(row: pd.Series) -> list[str]:
    status = str(row["status"])
    if status == "CONTROL":
        return ["random_control"]
    col = str(row["column"])
    item = str(row["item_id"])
    table = str(row["table"])
    if status == "BLOCKED_DATA":
        return []
    if table == "market_context":
        return ["index_tri"]
    if col == "industry":
        return ["industry_pit"]
    if col in {"market_cap_twd", "market_cap_tier", "turnover_value_ratio"}:
        return ["market_value", "tradability"]
    if col.startswith("rs_industry_") or col.startswith("industry_rs_market_") or col.startswith("industry_strength_rank_"):
        return ["adjusted_eod", "industry_pit", "index_tri", "tradability"]
    if col.startswith("rs_market_") or col.startswith("beta") or col.startswith("corr") or col.startswith("resid_vol"):
        return ["adjusted_eod", "index_tri", "tradability"]
    if item.startswith("L2-") or item == "L3-G01":
        return ["adjusted_eod", "tradability"]
    return ["adjusted_eod", "tradability"]


def availability_evidence(dictionary: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for row in dictionary.itertuples(index=False):
        raw = pd.Series(row._asdict())
        deps = feature_dependencies(raw)
        if str(raw["status"]) == "BLOCKED_DATA":
            final = "UNKNOWN"
            basis = "BLOCKED_DATA: source required by feature is unavailable."
        else:
            statuses = [SOURCE_EVIDENCE[d]["status"] for d in deps]
            final = combine_status(statuses)
            basis = " | ".join(
                f"{d}:{SOURCE_EVIDENCE[d]['evidence_type']}:{SOURCE_EVIDENCE[d]['status']}"
                for d in deps
            )
        rows.append({
            "item_id": raw["item_id"],
            "feature_key": raw["feature_key"],
            "column": raw["column"],
            "parameter_version": raw["parameter_version"],
            "table": raw["table"],
            "build_status": raw["status"],
            "input_sources": ";".join(deps) if deps else "BLOCKED_DATA",
            "decision_point": "AFTER_SESSION_CLOSE",
            "availability_status": final,
            "evidence": basis,
            "usable_for_exact_decision_time_pit": final == "PASS",
        })
    return pd.DataFrame(rows)


def _load_exclusions() -> set[str]:
    if _sha256(EXCLUSIONS_PATH) != EXPECTED_EXCLUSION_SHA:
        raise SystemExit("BLOCKED: exclusion SHA drift")
    frame = pd.read_csv(EXCLUSIONS_PATH, dtype={"ticker": str})
    return set(frame["ticker"].astype(str))


def _eligible_stock_dates(year: int, exclusions: set[str]) -> pd.DataFrame:
    adj_path = SOURCE_ROOT / "adj" / f"prices_adj_{year}.parquet"
    adjusted = pd.read_parquet(
        adj_path,
        columns=["date", "stock_id", "close", "Trading_money"],
    )
    adjusted["date"] = pd.to_datetime(adjusted["date"], errors="coerce").dt.normalize()
    adjusted["stock_id"] = adjusted["stock_id"].astype(str)
    tradability = pd.read_parquet(
        SOURCE_ROOT / "reference" / "tradability.parquet",
        columns=["date", "stock_id", "observed_trade", "valid_ohlc"],
    )
    tradability["date"] = pd.to_datetime(tradability["date"], errors="coerce").dt.normalize()
    tradability["stock_id"] = tradability["stock_id"].astype(str)
    tradability = tradability[tradability["date"].dt.year.eq(year)]
    panel = adjusted.merge(
        tradability,
        on=["date", "stock_id"],
        how="left",
        validate="one_to_one",
    )
    panel["observed_trade"] = panel["observed_trade"].fillna(False).astype(bool)
    panel["valid_ohlc"] = panel["valid_ohlc"].fillna(False).astype(bool)
    cfg = load_universe_config("configs/examples/universes/all_liquid.yaml")
    mask = UniverseCompiler().compile(
        cfg,
        panel,
        UniverseContext(
            p2_060_excluded_tickers=frozenset(exclusions),
            p2_060_exclusion_sha256=EXPECTED_EXCLUSION_SHA,
            theme_root=None,
        ),
    ).frame
    eligible = mask[mask["counts"].fillna(False).astype(bool)][["date", "stock_id"]].copy()
    eligible["year"] = year
    return eligible


def build_stratified_audit(cfg: dict, base_manifest: dict) -> pd.DataFrame:
    years = [int(x) for x in cfg["years"]]
    exclusions = _load_exclusions()
    stock_parts = []
    expected_rows = {
        int(Path(x["path"]).stem.split("_")[-1]): int(x["rows"])
        for x in base_manifest["stock_files"]
    }
    for year in years:
        eligible = _eligible_stock_dates(year, exclusions)
        if len(eligible) != expected_rows[year]:
            raise SystemExit(
                f"BLOCKED: eligible stock-date row count drift {year}: "
                f"{len(eligible)} != {expected_rows[year]}"
            )
        stock_parts.append(eligible)
    stock = pd.concat(stock_parts, ignore_index=True)
    stock_sample = stable_stratified_sample(
        stock,
        year_col="year",
        per_year=int(cfg["stock_samples_per_year"]),
        seed=int(cfg["sample_seed"]),
        id_cols=["date", "stock_id"],
        years=years,
    )
    stock_sample["scope"] = "stock_features"
    stock_sample["availability_status"] = "UNKNOWN"
    stock_sample["evidence_summary"] = (
        "Common stock feature inputs include adjusted EOD/tradability; "
        "source schemas do not retain actual provider available_at timestamps."
    )

    tri = load_finmind_total_return_index(
        SOURCE_ROOT / "futures" / "index_tri.parquet",
        stock_id="TAIEX",
    )
    market = pd.DataFrame({"date": pd.to_datetime(tri.index).normalize()})
    market = market[
        market["date"].between(pd.Timestamp("2016-01-04"), pd.Timestamp("2021-12-31"))
    ].copy()
    market["year"] = market["date"].dt.year
    market["stock_id"] = "MARKET_CONTEXT"
    market_sample = stable_stratified_sample(
        market,
        year_col="year",
        per_year=int(cfg["market_context_samples_per_year"]),
        seed=int(cfg["sample_seed"]) + 1,
        id_cols=["date", "stock_id"],
        years=years,
    )
    market_sample["scope"] = "market_context"
    market_sample["availability_status"] = "UNKNOWN"
    market_sample["evidence_summary"] = (
        "TaiwanStockTotalReturnIndex has date/value but no retained actual available_at timestamp."
    )

    audit = pd.concat([stock_sample, market_sample], ignore_index=True)
    audit["sample_seed"] = int(cfg["sample_seed"])
    audit["decision_point"] = cfg["decision_point"]
    audit["violation"] = audit["availability_status"].eq("FAIL")
    return audit[
        [
            "scope", "year", "date", "stock_id", "sample_seed",
            "decision_point", "availability_status", "violation",
            "evidence_summary",
        ]
    ].sort_values(["year", "scope", "date", "stock_id"], kind="stable").reset_index(drop=True)


def _min_date(path: Path, column: str = "date") -> pd.Timestamp | None:
    frame = pd.read_parquet(path, columns=[column])
    values = pd.to_datetime(frame[column], errors="coerce")
    return None if values.dropna().empty else values.min().normalize()


def warmup_diagnostic(cfg: dict, daily: pd.DataFrame, coverage: pd.DataFrame) -> pd.DataFrame:
    tri = load_finmind_total_return_index(
        SOURCE_ROOT / "futures" / "index_tri.parquet",
        stock_id="TAIEX",
    )
    sources = [
        {
            "kind": "SOURCE",
            "name": "adjusted_research_price",
            "earliest_date": _min_date(SOURCE_ROOT / "adj" / "prices_adj_2015.parquet"),
            "formula_requirement": "max stock lookback = 250 sessions + 10-session MA slope lag",
            "diagnosis": "SOURCE_HISTORY_INSUFFICIENT_BEFORE_E1",
        },
        {
            "kind": "SOURCE",
            "name": "raw_execution_price",
            "earliest_date": _min_date(SOURCE_ROOT / "raw" / "prices_raw_2015.parquet"),
            "formula_requirement": "not eligible as substitute for adjusted research coordinate",
            "diagnosis": "EARLIER_BUT_DIFFERENT_PRICE_COORDINATE",
        },
        {
            "kind": "SOURCE",
            "name": "market_value",
            "earliest_date": _min_date(SOURCE_ROOT / "fundamentals" / "market_value_2015.parquet"),
            "formula_requirement": "same-date descriptive input",
            "diagnosis": "SOURCE_START",
        },
        {
            "kind": "SOURCE",
            "name": "industry_snapshot_available_date",
            "earliest_date": _min_date(
                SOURCE_ROOT / "reference" / "industry_monthly_snapshots.parquet",
                "available_date",
            ),
            "formula_requirement": "causal interval; no backfill before first observation",
            "diagnosis": "SOURCE_START",
        },
        {
            "kind": "SOURCE",
            "name": "market_total_return_index",
            "earliest_date": pd.to_datetime(tri.index).min().normalize(),
            "formula_requirement": "market max lookback = 252 sessions",
            "diagnosis": "SOURCE_HISTORY_INSUFFICIENT_BEFORE_E1",
        },
    ]
    rows = []
    for x in sources:
        rows.append({
            "kind": x["kind"],
            "name": x["name"],
            "earliest_date": x["earliest_date"].date().isoformat() if x["earliest_date"] is not None else "",
            "first_any_valid_date": "",
            "2016_missing_rate": "",
            "warmup_insufficient_2016": "",
            "formula_requirement": x["formula_requirement"],
            "diagnosis": x["diagnosis"],
        })

    for feature in [
        "close_to_ma250", "ma_order_score", "ma250_slope10",
        "distance_250_high", "distance_250_low",
        "market_to_ma200", "market_position252",
    ]:
        d = daily[daily["feature"].eq(feature)].copy()
        d["date"] = pd.to_datetime(d["date"], errors="coerce")
        valid = d[d["n_valid"].astype(int).gt(0)]
        first = valid["date"].min() if not valid.empty else pd.NaT
        c = coverage[
            coverage["year"].astype(int).eq(2016)
            & coverage["feature"].eq(feature)
        ]
        missing = "" if c.empty else float(c.iloc[0]["missing_rate"])
        warm = "" if c.empty or "WARMUP_INSUFFICIENT" not in c.columns else int(c.iloc[0]["WARMUP_INSUFFICIENT"])
        rows.append({
            "kind": "FEATURE",
            "name": feature,
            "earliest_date": "",
            "first_any_valid_date": "" if pd.isna(first) else first.date().isoformat(),
            "2016_missing_rate": missing,
            "warmup_insufficient_2016": warm,
            "formula_requirement": "see dictionary lookback",
            "diagnosis": (
                "SOURCE_HISTORY_LIMIT_PLUS_LISTING_HISTORY"
                if feature.startswith(("close_to_ma250", "ma_order_score", "ma250_slope10", "distance_250_"))
                else "MARKET_SOURCE_HISTORY_LIMIT"
            ),
        })
    return pd.DataFrame(rows)


def ma120_audit(dictionary: pd.DataFrame, evidence: pd.DataFrame) -> pd.DataFrame:
    row = dictionary[dictionary["column"].eq("close_to_ma120")]
    if len(row) != 1:
        raise SystemExit("BLOCKED: close_to_ma120 dictionary row missing/duplicated")
    formula = str(row.iloc[0]["formula"])
    ev = evidence[evidence["column"].eq("close_to_ma120")].iloc[0]
    synthetic = pd.DataFrame({
        "close_to_ma120": [-0.01, 0.0, 0.02, pd.NA],
    })
    passed = column_threshold(
        panel=synthetic,
        spec=ComponentSpec(type="COLUMN_THRESHOLD", params={"column": "close_to_ma120", "min": 0.0}),
        cache=None,
        context=None,
    ).tolist()
    if passed != [False, True, True, False]:
        raise AssertionError(f"COLUMN_THRESHOLD MA120 semantics drifted: {passed}")
    return pd.DataFrame([{
        "feature": "close_to_ma120",
        "formula": formula,
        "correct_threshold": ">= 0.0",
        "wrong_threshold_examples": ">=1; percentile>=0",
        "raw_value_retained": True,
        "column_threshold_semantics_verified": True,
        "null_filter_result": False,
        "price_coordinate": "ADJUSTED_RESEARCH",
        "availability_status": ev["availability_status"],
        "canonical_panel_auto_hydrates_feature_artifact": False,
        "reuse_conclusion": "計算已存在，但仍缺串接",
        "reason": (
            "ResearchConfigEngine consumes a caller-supplied panel and has no loader/join "
            "for the layer1 parquet. If close_to_ma120 is explicitly joined into that panel, "
            "COLUMN_THRESHOLD min=0.0 has the correct numerical semantics."
        ),
    }])


def render_report(
    *,
    cfg: dict,
    base_manifest: dict,
    audit: pd.DataFrame,
    evidence: pd.DataFrame,
    warmup: pd.DataFrame,
    coverage_comparison: pd.DataFrame,
    ma120: pd.DataFrame,
    review_manifest: dict,
) -> str:
    summary = (
        audit.groupby(["year", "scope", "availability_status"])
        .size().rename("n").reset_index()
    )
    lines = [
        "# PIT 特徵矩陣第 5 項驗收修正 — review1",
        "",
        "狀態：修正完成，待審查驗收。這是品質稽核修正，不是新研究，也沒有重跑策略效果。",
        "",
        "## 版本與不變項",
        "",
        f"- base feature version：`{cfg['base_feature_version']}`",
        f"- review version：`{cfg['name']}`",
        f"- source revision：`{base_manifest['source_revision']}`",
        f"- feature formula version：`{base_manifest['formula_version']}`（未修改）",
        f"- base config：`{base_manifest['config_path']}`，SHA256 `{base_manifest['config_sha256']}`",
        f"- review config：`{CONFIG_PATH}`",
        "- feature parquet：**未重建、未覆蓋**；review1 只新增 QA/audit 產物。",
        "- E1 仍是 2016-01-04～2021-12-31；未查 E2/E3 效果。",
        "",
        "## available_at 修正",
        "",
        f"- 固定 seed：{cfg['sample_seed']}",
        f"- stock_features：每年 {cfg['stock_samples_per_year']} 筆",
        f"- market_context：每年 {cfg['market_context_samples_per_year']} 筆",
        f"- 總 audit sample：**{len(audit)}** 筆；FAIL={int(audit['availability_status'].eq('FAIL').sum())}、UNKNOWN={int(audit['availability_status'].eq('UNKNOWN').sum())}、PASS={int(audit['availability_status'].eq('PASS').sum())}。",
        "",
        "| 年 | scope | PASS | FAIL | UNKNOWN |",
        "|---:|---|---:|---:|---:|",
    ]
    for (year, scope), g in audit.groupby(["year", "scope"]):
        lines.append(
            f"| {year} | {scope} | {int(g['availability_status'].eq('PASS').sum())} | "
            f"{int(g['availability_status'].eq('FAIL').sum())} | "
            f"{int(g['availability_status'].eq('UNKNOWN').sum())} |"
        )
    lines += [
        "",
        "### 可用時間證據結論",
        "",
        "- 這次不再把「交易日期 <= 輸出日期」當成 PIT PASS。",
        "- adjusted EOD、tradability、market_value、TAIEX TRI 的 source parquet 都沒有保留實際 provider available_at/known-time；因此精確到 AFTER_SESSION_CLOSE 決策時點一律為 **UNKNOWN**，不是 PASS。",
        "- PIT industry 的 valid_from 由官方 MOPS snapshot available_date / reclassification effective_date 因果建置，**date-level causal order 有證據**；但 source 沒有時分秒，因此同日 AFTER_SESSION_CLOSE 的精確可用性仍是 **UNKNOWN**。",
        "- fixed-seed random controls 不讀外部資料，raw control value 為 PASS；若使用其同日橫截面 percentile，仍會依賴 eligible-universe 輸入的可用時間。",
        "- 所以目前真實 COMPLETE features 不可被宣稱為『已證實可在精確 AFTER_SESSION_CLOSE 決策時點 PIT 安全』。它們仍可作描述性／資料建置用途，待來源時間戳或更強的發布契約補齊。",
        "",
        "完整逐 feature 證據見 availability_evidence CSV。",
        "",
        "## 長窗暖機診斷",
        "",
        "- adjusted research price 實際最早：**2015-06-01**。",
        "- RAW execution price 可早到 **2015-01-05**，但 RAW 與 ADJUSTED_RESEARCH 是不同價格座標，不能拿 RAW 補 MA250 等 adjusted 技術特徵。",
        "- market_value 實際最早：2015-06-01。",
        "- industry monthly snapshot available_date 可早於 adjusted price；但股票技術矩陣仍受 adjusted 起點限制。",
        "- TAIEX total-return index 的實際起點與 252 日市場長窗限制詳見 warmup_diagnostic CSV。",
        "- 因此原 v1 的 2015-06-01 不是 loader 人為截短，而是 adjusted source 本身的起點；本次沒有可合法擴大的 adjusted 暖機資料，所以不重建 feature parquet。",
        "- MA250 家族 2016 早期 null 必須保留；來源歷史不足之外，部分較晚上市股票另有個股歷史不足。null 不得補零、前填或視為條件不成立。",
        "",
        "## 修正前後 coverage",
        "",
        "- feature values 與公式未改、parquet 未重建，因此逐年 coverage **前後完全相同**；review1 只修正 audit 與文件口徑。",
        "",
        "| 年 | feature rows | before median missing | after median missing | before max | after max |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for r in coverage_comparison.itertuples(index=False):
        lines.append(
            f"| {r.year} | {r.feature_rows} | {r.before_median_missing_rate:.2%} | "
            f"{r.after_median_missing_rate:.2%} | {r.before_max_missing_rate:.2%} | "
            f"{r.after_max_missing_rate:.2%} |"
        )
    m = ma120.iloc[0]
    lines += [
        "",
        "## MA120 重用驗收",
        "",
        f"- dictionary 原值公式：`{m['formula']}`。",
        "- 正確條件「收盤 >= MA120」就是 **close_to_ma120 >= 0.0**；不是 >=1，也不是 percentile >=0。",
        "- raw `close_to_ma120` 欄位會保留在 feature parquet；COLUMN_THRESHOLD 對 synthetic gate 已驗證：[-0.01, 0, 0.02, null] -> [false, true, true, false]。",
        "- `SignalEvaluator._normalize_panel` 保留額外欄位，所以只要欄位已在 caller-supplied panel 中，COLUMN_THRESHOLD 可直接讀。",
        "- 但 `ResearchConfigEngine.prepare()` 本身**不會自動載入／join 第 5 項 parquet**；現有 canonical strategy runner 仍傳入原 research panel。",
        "- 結論：**計算已存在，但仍缺串接**。不需要新增 PRICE_ABOVE_MA evaluator；需要的是 feature artifact -> canonical panel 的明確 hydration/join。",
        "- 缺值時 COLUMN_THRESHOLD 回 false；這只代表『filter 不通過』，不能在報告中把 null 說成『價格低於 MA120』。",
        f"- close_to_ma120 精確決策時點 available_at：**{m['availability_status']}**。",
        "",
        "## Baseline 缺口更正",
        "",
        "- `BASELINE_COMPONENT_GAPS.md` 已移除『PRICE_ABOVE_MA 確實缺 evaluator』的舊結論。",
        "- C 類確實缺 evaluator 由 10 改為 **9**；B 類可重用計算但缺介面由 4 改為 **5**。",
        "- 60 日突破 baseline 的最小缺口改為：**2 個確實缺的 exit evaluator + 1 個 feature-panel 串接工作**；不再寫『最少新增 3 個 evaluator』。",
        "- 本次沒有新增 baseline evaluator，也沒有跑 baseline。",
        "",
        "## 測試與產物",
        "",
        f"- review workflow：{review_manifest['workflow_run_url']}",
        f"- review artifact：`{review_manifest['artifact_name']}`",
        f"- review manifest：`{cfg['outputs']['manifest']}`",
        f"- stratified audit：`{cfg['outputs']['audit']}`",
        f"- availability evidence：`{cfg['outputs']['availability_evidence']}`",
        f"- warmup diagnostic：`{cfg['outputs']['warmup_diagnostic']}`",
        f"- coverage comparison：`{cfg['outputs']['coverage_comparison']}`",
        f"- MA120 audit：`{cfg['outputs']['ma120_audit']}`",
        "",
        "review unit tests 必須包含：跨年分層抽樣不會被第一年吃完整 quota；UNKNOWN 不會被聚合成 PASS；MA120 threshold=0 語意。",
        "",
        "## 尚未解決限制",
        "",
        "- 真實 features 的精確 provider availability timestamp 仍未建立，所以 decision-time PIT 為 UNKNOWN。",
        "- L3-G02 theme_membership 仍為 BLOCKED_DATA。",
        "- 第 5 項 feature parquet 本身仍使用原 v1 artifact；review1 沒有改值也沒有延長其保存期限。",
        "- 未啟動 ML、baseline 回測、VCP Round 2；未讀 E2/E3 效果。",
        "",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    base_manifest = json.loads(Path(cfg["base_manifest"]).read_text(encoding="utf-8"))
    source_revision = os.environ.get("SOURCE_REVISION", "").strip()
    if not source_revision or source_revision != base_manifest["source_revision"]:
        raise SystemExit(
            f"BLOCKED: review source revision must equal base manifest: "
            f"{source_revision} != {base_manifest['source_revision']}"
        )
    dictionary = pd.read_csv(cfg["base_dictionary"])
    coverage = pd.read_csv(cfg["base_coverage"])
    daily = pd.read_csv(cfg["base_daily_valid_counts"])

    evidence = availability_evidence(dictionary)
    audit = build_stratified_audit(cfg, base_manifest)
    if len(audit) < 1000:
        raise SystemExit("BLOCKED: availability audit has fewer than 1000 samples")
    if sorted(audit["year"].unique().tolist()) != [int(x) for x in cfg["years"]]:
        raise SystemExit("BLOCKED: availability audit lost a year")
    if not {"stock_features", "market_context"} <= set(audit["scope"]):
        raise SystemExit("BLOCKED: market_context not represented in audit")
    if int(audit["availability_status"].eq("UNKNOWN").sum()) == 0:
        raise SystemExit("BLOCKED: review unexpectedly has no UNKNOWN availability")

    warmup = warmup_diagnostic(cfg, daily, coverage)
    annual = (
        coverage[coverage["status"].ne("BLOCKED_DATA")]
        .groupby("year", as_index=False)
        .agg(
            feature_rows=("feature", "size"),
            before_median_missing_rate=("missing_rate", "median"),
            before_max_missing_rate=("missing_rate", "max"),
        )
    )
    annual["after_median_missing_rate"] = annual["before_median_missing_rate"]
    annual["after_max_missing_rate"] = annual["before_max_missing_rate"]
    annual["feature_data_rebuilt"] = False

    ma120 = ma120_audit(dictionary, evidence)

    out = cfg["outputs"]
    Path(out["audit"]).parent.mkdir(parents=True, exist_ok=True)
    audit.to_csv(out["audit"], index=False)
    evidence.to_csv(out["availability_evidence"], index=False)
    warmup.to_csv(out["warmup_diagnostic"], index=False)
    annual.to_csv(out["coverage_comparison"], index=False)
    ma120.to_csv(out["ma120_audit"], index=False)

    run_id = os.environ.get("GITHUB_RUN_ID", "local")
    repository = os.environ.get("GITHUB_REPOSITORY", "bibobo2266/AstraQuant")
    artifact_name = f"pit-feature-matrix-layer1-v1-review1-{run_id}"
    manifest = {
        "review_name": cfg["name"],
        "base_feature_version": cfg["base_feature_version"],
        "base_manifest": cfg["base_manifest"],
        "base_source_revision": base_manifest["source_revision"],
        "base_formula_version": base_manifest["formula_version"],
        "base_config_sha256": base_manifest["config_sha256"],
        "review_config": str(CONFIG_PATH),
        "review_config_sha256": _sha256(CONFIG_PATH),
        "sample_seed": cfg["sample_seed"],
        "audit_rows": len(audit),
        "audit_by_year_scope_status": (
            audit.groupby(["year", "scope", "availability_status"])
            .size()
            .rename("n")
            .reset_index()
            .to_dict("records")
        ),
        "availability_pass": int(audit["availability_status"].eq("PASS").sum()),
        "availability_fail": int(audit["availability_status"].eq("FAIL").sum()),
        "availability_unknown": int(audit["availability_status"].eq("UNKNOWN").sum()),
        "feature_availability_counts": evidence["availability_status"].value_counts().to_dict(),
        "feature_data_rebuilt": False,
        "feature_values_changed": False,
        "round2_executed": False,
        "effect_metrics_computed": False,
        "workflow_run_id": run_id,
        "workflow_run_url": f"https://github.com/{repository}/actions/runs/{run_id}",
        "artifact_name": artifact_name,
    }
    Path(out["manifest"]).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    Path(out["report"]).write_text(
        render_report(
            cfg=cfg,
            base_manifest=base_manifest,
            audit=audit,
            evidence=evidence,
            warmup=warmup,
            coverage_comparison=annual,
            ma120=ma120,
            review_manifest=manifest,
        ),
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
