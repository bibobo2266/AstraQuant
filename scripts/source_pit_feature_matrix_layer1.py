#!/usr/bin/env python3
from __future__ import annotations

import gc
import hashlib
import json
import os
from pathlib import Path
import resource
import time

import numpy as np
import pandas as pd
import yaml

from astraquant.research.benchmark import load_finmind_total_return_index
from astraquant.research.config_io import load_universe_config
from astraquant.research.epoch_governance import resolve_historical_effect_period
from astraquant.research.universe_engine import UniverseCompiler, UniverseContext

from pit_feature_matrix_layer1 import (
    AVAILABILITY_POLICY,
    FORMULA_VERSION,
    RANK_MIN_N,
    Layer1Parameters,
    add_industry_and_cross_section_features,
    add_random_controls_and_ranks,
    attach_industry_pit,
    build_market_context,
    build_stock_features,
    dictionary_frame,
    market_primary_columns,
    missing_reason_counts,
)


ROOT = Path(".").resolve()
CONFIG_PATH = Path(
    os.environ.get(
        "FEATURE_MATRIX_CONFIG",
        "configs/research/pit_feature_matrix_layer1_v1.yaml",
    )
)
SOURCE_ROOT = Path(
    os.environ.get(
        "SOURCE_ROOT",
        "source_runtime/minervini_picks/data",
    )
).resolve()
SOURCE_REVISION = os.environ.get("SOURCE_REVISION", "").strip()
EXCLUSIONS_PATH = Path("docs/SOURCE_CA_PIT_EXCLUSIONS.csv")
EXPECTED_EXCLUSION_SHA = "379d58f6a8aa06b1e020d56911930f4bc01861d3eeca109613d9e5b1e490d134"
REPORT_PATH = Path("docs/PIT_FEATURE_MATRIX_LAYER1_V1.md")
OUT_ROOT = Path("out")
ARTIFACT_ROOT = Path("artifacts/pit_feature_matrix_layer1_v1")
PART_ROOT = ARTIFACT_ROOT / "_parts"
CHUNK_SIZE = int(os.environ.get("FEATURE_TICKER_CHUNK", "200"))

period = resolve_historical_effect_period("E1")
assert period.end is not None
E1_START = pd.Timestamp(period.start)
E1_END = pd.Timestamp(period.end)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _load_cfg() -> tuple[dict[str, object], Layer1Parameters]:
    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    if cfg.get("epoch") != "E1":
        raise SystemExit("BLOCKED: layer1 feature matrix must remain E1")
    p = dict(cfg["parameters"])
    for key in ("ma_windows", "rv_windows", "rsi_windows", "relative_strength_horizons"):
        p[key] = tuple(int(x) for x in p[key])
    return cfg, Layer1Parameters(**p)


def _load_exclusions() -> set[str]:
    digest = _sha256(EXCLUSIONS_PATH)
    if digest != EXPECTED_EXCLUSION_SHA:
        raise SystemExit(
            "BLOCKED: P2-060 exclusion ledger hash mismatch "
            f"expected={EXPECTED_EXCLUSION_SHA} got={digest}"
        )
    frame = pd.read_csv(EXCLUSIONS_PATH, dtype={"ticker": str})
    return set(frame["ticker"].astype(str))


def _load_adjusted(warmup_start: pd.Timestamp) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    for year in range(warmup_start.year, E1_END.year + 1):
        path = SOURCE_ROOT / "adj" / f"prices_adj_{year}.parquet"
        if not path.exists():
            raise SystemExit(f"BLOCKED: missing adjusted source {path}")
        part = pd.read_parquet(
            path,
            columns=[
                "date", "stock_id", "open", "max", "min", "close",
                "Trading_Volume", "Trading_money",
            ],
        )
        part["date"] = pd.to_datetime(part["date"], errors="coerce").dt.normalize()
        part["stock_id"] = part["stock_id"].astype(str)
        part = part[
            part["date"].between(warmup_start, E1_END, inclusive="both")
        ].copy()
        parts.append(part)
    out = pd.concat(parts, ignore_index=True)
    if out.duplicated(["date", "stock_id"]).any():
        raise SystemExit("BLOCKED: duplicate adjusted logical keys")
    return out


def _load_tradability(warmup_start: pd.Timestamp) -> pd.DataFrame:
    path = SOURCE_ROOT / "reference" / "tradability.parquet"
    frame = pd.read_parquet(
        path,
        columns=["date", "stock_id", "observed_trade", "valid_ohlc"],
    )
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
    frame["stock_id"] = frame["stock_id"].astype(str)
    frame = frame[
        frame["date"].between(warmup_start, E1_END, inclusive="both")
    ].copy()
    if frame.duplicated(["date", "stock_id"]).any():
        raise SystemExit("BLOCKED: duplicate tradability logical keys")
    return frame


def _load_market_value(warmup_start: pd.Timestamp) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    for year in range(warmup_start.year, E1_END.year + 1):
        path = SOURCE_ROOT / "fundamentals" / f"market_value_{year}.parquet"
        if not path.exists():
            raise SystemExit(f"BLOCKED: missing market-value source {path}")
        part = pd.read_parquet(path)
        required = {"date", "stock_id", "market_value"}
        missing = required - set(part.columns)
        if missing:
            raise SystemExit(
                f"BLOCKED: market-value source missing {sorted(missing)} in {path}"
            )
        part = part[["date", "stock_id", "market_value"]].copy()
        part["date"] = pd.to_datetime(part["date"], errors="coerce").dt.normalize()
        part["stock_id"] = part["stock_id"].astype(str)
        part["market_value"] = pd.to_numeric(part["market_value"], errors="coerce")
        part = part[
            part["date"].between(warmup_start, E1_END, inclusive="both")
        ].copy()
        parts.append(part)
    out = pd.concat(parts, ignore_index=True)
    if out.duplicated(["date", "stock_id"]).any():
        raise SystemExit("BLOCKED: duplicate market-value logical keys")
    return out


def _load_industry_pit() -> pd.DataFrame:
    path = SOURCE_ROOT / "reference" / "industry_pit.parquet"
    if not path.exists():
        raise SystemExit("BLOCKED_DATA: PIT industry file missing")
    frame = pd.read_parquet(path)
    required = {"stock_id", "valid_from", "valid_to", "industry"}
    missing = required - set(frame.columns)
    if missing:
        raise SystemExit(
            f"BLOCKED_DATA: PIT industry columns missing: {sorted(missing)}"
        )
    return frame


def _load_market_context(p: Layer1Parameters) -> pd.DataFrame:
    path = SOURCE_ROOT / "futures" / "index_tri.parquet"
    if not path.exists():
        raise SystemExit("BLOCKED_DATA: total-return benchmark missing")
    tri = load_finmind_total_return_index(path, stock_id="TAIEX")
    tri = tri.loc[
        (tri.index >= pd.Timestamp("2015-01-01"))
        & (tri.index <= E1_END)
    ]
    return build_market_context(tri, p=p)


def _available_audit_sample(frame: pd.DataFrame, limit: int) -> pd.DataFrame:
    if frame.empty or limit <= 0:
        return pd.DataFrame()
    keys = frame["date"].astype(str) + "|" + frame["stock_id"].astype(str)
    order = pd.util.hash_pandas_object(keys, index=False)
    sample = frame.loc[order.sort_values().index[: min(limit, len(frame))]].copy()
    output_date = pd.to_datetime(sample["available_at_date"], errors="coerce").dt.normalize()
    industry_date = pd.to_datetime(
        sample["industry_valid_from"], errors="coerce"
    ).dt.normalize()
    market_value_date = sample["date"].where(sample["market_value"].notna())
    market_date = sample["date"].where(sample["market_ret1"].notna())
    input_max = pd.concat(
        [
            sample["date"].rename("price"),
            industry_date.rename("industry"),
            pd.to_datetime(market_value_date).rename("market_value"),
            pd.to_datetime(market_date).rename("market_tri"),
        ],
        axis=1,
    ).max(axis=1)
    out = pd.DataFrame(
        {
            "date": sample["date"].to_numpy(),
            "stock_id": sample["stock_id"].astype(str).to_numpy(),
            "max_input_available_date": input_max.to_numpy(),
            "output_available_date": output_date.to_numpy(),
        }
    )
    out["violation"] = (
        pd.to_datetime(out["max_input_available_date"], errors="coerce")
        > pd.to_datetime(out["output_available_date"], errors="coerce")
    ).fillna(False)
    return out


def _coverage_rows(
    frame: pd.DataFrame,
    *,
    year: int,
    dictionary: pd.DataFrame,
    p: Layer1Parameters,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, object]] = []
    complete = dictionary[
        dictionary["status"].isin(["COMPLETE", "CONTROL"])
        & dictionary["table"].eq("stock_features")
    ]
    for spec in complete.itertuples(index=False):
        col = str(spec.column)
        if col not in frame.columns:
            continue
        n_total = len(frame)
        n_valid = int(frame[col].notna().sum())
        rows.append(
            {
                "year": year,
                "item_id": spec.item_id,
                "feature_key": spec.feature_key,
                "feature": col,
                "parameter_version": spec.parameter_version,
                "status": spec.status,
                "n_eligible": n_total,
                "n_valid": n_valid,
                "missing_rate": (
                    float(1 - n_valid / n_total) if n_total else np.nan
                ),
            }
        )
    reason_cols = [
        str(x.column)
        for x in complete.itertuples(index=False)
        if x.status == "COMPLETE" and str(x.column) in frame.columns
    ]
    reasons = missing_reason_counts(frame, columns=reason_cols, p=p)
    return pd.DataFrame(rows), reasons


def _daily_counts(
    frame: pd.DataFrame,
    *,
    dictionary: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    specs = dictionary[
        dictionary["status"].isin(["COMPLETE", "CONTROL"])
        & dictionary["table"].eq("stock_features")
    ]
    eligible_by_date = frame.groupby("date")["stock_id"].size().rename("n_eligible")
    for spec in specs.itertuples(index=False):
        col = str(spec.column)
        if col not in frame.columns:
            continue
        n_valid = frame[col].notna().groupby(frame["date"]).sum().rename("n_valid")
        temp = pd.concat([eligible_by_date, n_valid], axis=1).reset_index()
        temp["feature"] = col
        temp["item_id"] = spec.item_id
        temp["rank_required"] = bool(spec.cross_section_rank)
        temp["rank_usable"] = (
            temp["n_valid"].ge(RANK_MIN_N)
            if bool(spec.cross_section_rank)
            else temp["n_valid"].gt(0)
        )
        rows.append(temp)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def _market_daily_counts(
    market: pd.DataFrame,
    dictionary: pd.DataFrame,
) -> pd.DataFrame:
    specs = dictionary[
        dictionary["status"].eq("COMPLETE")
        & dictionary["table"].eq("market_context")
    ]
    rows = []
    for spec in specs.itertuples(index=False):
        col = str(spec.column)
        if col not in market.columns:
            continue
        temp = market.loc[
            market["date"].between(E1_START, E1_END, inclusive="both"),
            ["date", col],
        ].copy()
        temp["n_eligible"] = 1
        temp["n_valid"] = temp[col].notna().astype(int)
        temp["feature"] = col
        temp["item_id"] = spec.item_id
        temp["rank_required"] = False
        temp["rank_usable"] = temp["n_valid"].gt(0)
        rows.append(
            temp[
                [
                    "date", "n_eligible", "n_valid", "feature",
                    "item_id", "rank_required", "rank_usable",
                ]
            ]
        )
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def _report(
    *,
    dictionary: pd.DataFrame,
    coverage: pd.DataFrame,
    daily: pd.DataFrame,
    audit: pd.DataFrame,
    manifest: dict[str, object],
) -> str:
    real = dictionary[dictionary["status"].eq("COMPLETE")]
    controls = dictionary[dictionary["status"].eq("CONTROL")]
    blocked = dictionary[dictionary["status"].eq("BLOCKED_DATA")]
    completed_ids = sorted(set(real["item_id"]))
    blocked_ids = sorted(set(blocked["item_id"]))
    real_keys = int(real["feature_key"].nunique())
    versions = int(len(real))
    violations = int(audit["violation"].sum()) if not audit.empty else 0
    unusable = daily[~daily["rank_usable"].astype(bool)] if not daily.empty else pd.DataFrame()

    annual = (
        coverage[coverage["status"].ne("BLOCKED_DATA")]
        .groupby("year", as_index=False)
        .agg(
            feature_rows=("feature", "size"),
            median_missing_rate=("missing_rate", "median"),
            max_missing_rate=("missing_rate", "max"),
        )
    )
    annual_lines = [
        "| 年 | 特徵版本列 | 缺值率中位數 | 最大缺值率 |",
        "|---:|---:|---:|---:|",
    ]
    for r in annual.itertuples(index=False):
        annual_lines.append(
            f"| {int(r.year)} | {int(r.feature_rows)} | "
            f"{float(r.median_missing_rate):.2%} | {float(r.max_missing_rate):.2%} |"
        )

    return "\n".join(
        [
            "# PIT 安全特徵矩陣第一層 v1",
            "",
            "狀態：COMPLETE — E1 資料建置與資料品質稽核；不是效果掃描。",
            "",
            "## 結論邊界",
            "",
            "- 本項只建立 L2 技術狀態與 L3 可由既有 PIT 資料支持的市場結構／背景。",
            "- 未計算勝率、期望值、IC、特徵排名、存活名單或最佳參數。",
            "- VCP Round 1 維持凍結；Round 2 未執行。",
            "- 所有 rolling 先在完整歷史序列計算，再套 all_liquid + P2-060 當日母體。",
            "- 股票技術價格使用既有 adjusted research coordinate；大盤只使用 FinMind TAIEX 含息指數。",
            "",
            "## 範圍",
            "",
            f"- 完成 TEST_INVENTORY IDs：{', '.join(completed_ids)}",
            f"- BLOCKED_DATA IDs：{', '.join(blocked_ids) if blocked_ids else '無'}",
            f"- 真實原始特徵數（distinct feature_key）：**{real_keys}**",
            f"- 真實參數版本數（dictionary COMPLETE rows）：**{versions}**",
            f"- 固定種子亂數對照：**{len(controls)}**",
            "",
            "L3-G02 主題名單沒有可持久讀取的 dated membership source，因此本輪明確標 BLOCKED_DATA；沒有用目前名單回貼歷史。",
            "",
            "## 來源與 available_at",
            "",
            f"- source revision：{manifest['source_revision']}",
            f"- formula version：{FORMULA_VERSION}",
            "- E1：2016-01-04～2021-12-31；只讀 E1 之前資料作 rolling 暖機。",
            "- adjusted OHLCV / Trading_money：當日收盤後可用。",
            "- market_value：FinMind 當日市值欄；本矩陣只宣告同日 provider publication 後／次一交易決策可用，不宣稱盤中可用。",
            "- PIT industry：只在 industry_pit.valid_from 之後使用，缺歷史不回填。",
            "- market_context：FinMind TaiwanStockTotalReturnIndex (TAIEX)，含息口徑；market_context 不做股票橫截面排名。",
            "",
            "## 資料品質",
            "",
            f"- available_at 抽樣：{len(audit):,} 筆；違反數：**{violations}**。",
            f"- 每日有效標的不足而不可排名／不可用的 feature-date：**{len(unusable):,}**；詳見 unusable_dates CSV。",
            f"- cache hits/misses：{manifest['cache_hits']:,} / {manifest['cache_misses']:,}；repeat-hit gate={manifest['cache_repeat_hit_gate']}.",
            f"- 執行秒數：{manifest['runtime_seconds']:.1f}；peak RSS：{manifest['peak_rss_mb']:.1f} MiB。",
            "",
            "### 逐年覆蓋摘要",
            "",
            *annual_lines,
            "",
            "## 產物",
            "",
            f"- GitHub Actions artifact：{manifest['artifact_name']}",
            f"- workflow run：{manifest['workflow_run_url']}",
            "- artifact 內含 stock_features_2016.parquet～stock_features_2021.parquet 與 market_context.parquet。",
            "- repo 內保留 manifest、feature dictionary、逐年 coverage、每日有效數、不可用日期與 available_at audit。",
            "",
            "## 研究防線",
            "",
            "本項沒有 outcome 欄位，也沒有讀取 E2/E3 效果。任何後續疊加或 ML 都必須另依 queue 啟動；本項不自動開始。",
        ]
    ) + "\n"


def main() -> None:
    started = time.perf_counter()
    if not SOURCE_REVISION:
        raise SystemExit("BLOCKED: SOURCE_REVISION is required")
    cfg, p = _load_cfg()
    warmup_start = pd.Timestamp(cfg["warmup_start"])
    dictionary = dictionary_frame(p)
    exclusions = _load_exclusions()

    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    PART_ROOT.mkdir(parents=True, exist_ok=True)
    OUT_ROOT.mkdir(parents=True, exist_ok=True)

    adjusted = _load_adjusted(warmup_start)
    tradability = _load_tradability(warmup_start)
    market_value = _load_market_value(warmup_start)
    industry_pit = _load_industry_pit()
    market_context = _load_market_context(p)

    tickers = sorted(
        adjusted.loc[
            adjusted["stock_id"].str.fullmatch(r"[1-9]\d{3}", na=False),
            "stock_id",
        ].unique()
    )
    total_cache_hits = 0
    total_cache_misses = 0
    repeat_hit_gate = True

    for chunk_no, start in enumerate(range(0, len(tickers), CHUNK_SIZE), start=1):
        chunk = set(tickers[start : start + CHUNK_SIZE])
        panel = adjusted[adjusted["stock_id"].isin(chunk)].copy()
        panel = panel.merge(
            tradability[tradability["stock_id"].isin(chunk)],
            on=["date", "stock_id"],
            how="left",
            validate="one_to_one",
        )
        panel["observed_trade"] = panel["observed_trade"].fillna(False).astype(bool)
        panel["valid_ohlc"] = panel["valid_ohlc"].fillna(False).astype(bool)
        panel = panel.merge(
            market_value[market_value["stock_id"].isin(chunk)],
            on=["date", "stock_id"],
            how="left",
            validate="one_to_one",
        )
        panel = attach_industry_pit(panel, industry_pit)
        features, cache = build_stock_features(
            panel,
            source_revision=SOURCE_REVISION,
            market_context=market_context,
            p=p,
        )
        repeat_hit_gate &= cache.hits > 0
        total_cache_hits += cache.hits
        total_cache_misses += cache.misses

        features = features[
            features["date"].between(E1_START, E1_END, inclusive="both")
        ].copy()
        for year, part in features.groupby(features["date"].dt.year):
            path = PART_ROOT / f"features_{int(year)}_{chunk_no:03d}.parquet"
            part.to_parquet(path, index=False, compression="zstd")
        del panel, features, cache
        gc.collect()

    universe_cfg = load_universe_config(cfg["universe"])
    universe_context = UniverseContext(
        p2_060_excluded_tickers=frozenset(exclusions),
        p2_060_exclusion_sha256=EXPECTED_EXCLUSION_SHA,
        theme_root=None,
    )
    compiler = UniverseCompiler()

    coverage_parts: list[pd.DataFrame] = []
    reason_parts: list[pd.DataFrame] = []
    daily_parts: list[pd.DataFrame] = []
    audit_parts: list[pd.DataFrame] = []
    stock_files: list[dict[str, object]] = []

    for year in range(E1_START.year, E1_END.year + 1):
        files = sorted(PART_ROOT.glob(f"features_{year}_*.parquet"))
        if not files:
            raise SystemExit(f"BLOCKED: no feature parts for {year}")
        frame = pd.concat([pd.read_parquet(path) for path in files], ignore_index=True)
        minimal = frame[
            [
                "date", "stock_id", "close", "Trading_money",
                "observed_trade", "valid_ohlc",
            ]
        ].copy()
        mask = compiler.compile(
            universe_cfg,
            minimal,
            universe_context,
        ).frame[["date", "stock_id", "counts"]]
        frame = frame.merge(mask, on=["date", "stock_id"], how="left", validate="one_to_one")
        frame = frame[frame["counts"].fillna(False).astype(bool)].copy()
        frame, _ = add_industry_and_cross_section_features(frame, p=p)
        frame, _ = add_random_controls_and_ranks(
            frame,
            seeds=cfg["random_controls"]["seeds"],
        )

        complete_stock = dictionary[
            dictionary["status"].isin(["COMPLETE", "CONTROL"])
            & dictionary["table"].eq("stock_features")
        ]
        real_cols = [
            str(x) for x in complete_stock["column"]
            if str(x) in frame.columns
        ]
        pct_cols = [
            f"{col}_pct" for col in real_cols
            if f"{col}_pct" in frame.columns
        ]
        meta_cols = [
            "date", "stock_id", "available_at_date", "available_at_rule",
            "industry", "industry_valid_from", "bars_seen",
        ]
        final = frame[
            list(dict.fromkeys(meta_cols + real_cols + pct_cols))
        ].copy()
        final["source_revision"] = SOURCE_REVISION
        final["formula_version"] = FORMULA_VERSION
        banned = {
            "outcome", "forward_return", "net_return", "win_rate",
            "expectancy", "exit_date", "exit_price",
        }
        if banned & set(final.columns):
            raise SystemExit(
                f"BLOCKED: outcome/effect columns leaked into feature matrix: "
                f"{sorted(banned & set(final.columns))}"
            )
        dst = ARTIFACT_ROOT / f"stock_features_{year}.parquet"
        final.to_parquet(dst, index=False, compression="zstd")
        stock_files.append(
            {
                "path": str(dst),
                "size_bytes": dst.stat().st_size,
                "sha256": _sha256(dst),
                "rows": len(final),
            }
        )

        cov, reasons = _coverage_rows(
            frame,
            year=year,
            dictionary=dictionary,
            p=p,
        )
        coverage_parts.append(cov)
        reason_parts.append(reasons)
        daily_parts.append(_daily_counts(frame, dictionary=dictionary))
        if sum(len(x) for x in audit_parts) < 1000:
            remaining = 1000 - sum(len(x) for x in audit_parts)
            audit_parts.append(_available_audit_sample(frame, remaining))
        del frame, final, minimal, mask
        gc.collect()

    market_e1 = market_context[
        market_context["date"].between(E1_START, E1_END, inclusive="both")
    ].copy()
    market_cols = [
        "date", "available_at_date", "available_at_rule", "tri_value",
        *[c for c in market_primary_columns(p) if c in market_e1.columns],
        *[
            f"market_return_{h}"
            for h in p.relative_strength_horizons
            if f"market_return_{h}" in market_e1.columns
        ],
    ]
    market_out = market_e1[market_cols].copy()
    market_out["source_revision"] = SOURCE_REVISION
    market_out["formula_version"] = FORMULA_VERSION
    market_path = ARTIFACT_ROOT / "market_context.parquet"
    market_out.to_parquet(market_path, index=False, compression="zstd")
    daily_parts.append(_market_daily_counts(market_e1, dictionary))

    coverage = pd.concat(coverage_parts, ignore_index=True)
    reasons = pd.concat(reason_parts, ignore_index=True)
    if not reasons.empty:
        reason_wide = (
            reasons.pivot_table(
                index=["year", "feature"],
                columns="reason",
                values="count",
                aggfunc="sum",
                fill_value=0,
            )
            .reset_index()
        )
        coverage = coverage.merge(
            reason_wide,
            on=["year", "feature"],
            how="left",
            validate="one_to_one",
        )
    blocked = dictionary[dictionary["status"].eq("BLOCKED_DATA")]
    for year in range(E1_START.year, E1_END.year + 1):
        for spec in blocked.itertuples(index=False):
            row = {
                "year": year,
                "item_id": spec.item_id,
                "feature_key": spec.feature_key,
                "feature": spec.column,
                "parameter_version": spec.parameter_version,
                "status": "BLOCKED_DATA",
                "n_eligible": 0,
                "n_valid": 0,
                "missing_rate": 1.0,
            }
            coverage = pd.concat([coverage, pd.DataFrame([row])], ignore_index=True)

    daily = pd.concat(daily_parts, ignore_index=True)
    unusable = daily[~daily["rank_usable"].fillna(False).astype(bool)].copy()
    unusable["reason"] = np.where(
        unusable["rank_required"].astype(bool),
        "INSUFFICIENT_VALID_TARGETS_FOR_CROSS_SECTION_RANK",
        "NO_VALID_VALUE",
    )
    audit = pd.concat(audit_parts, ignore_index=True).head(1000)
    violations = int(audit["violation"].sum()) if not audit.empty else 0
    if violations:
        raise SystemExit(f"BLOCKED: available_at audit violations={violations}")

    dictionary.to_csv(cfg["storage"]["dictionary"], index=False, encoding="utf-8")
    coverage.to_csv(cfg["storage"]["coverage"], index=False, encoding="utf-8")
    daily.to_csv(cfg["storage"]["daily_valid_counts"], index=False, encoding="utf-8")
    unusable.to_csv(cfg["storage"]["unusable_dates"], index=False, encoding="utf-8")
    audit.to_csv(cfg["storage"]["available_at_audit"], index=False, encoding="utf-8")

    runtime = time.perf_counter() - started
    peak_rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    run_id = os.environ.get("GITHUB_RUN_ID", "local")
    repository = os.environ.get("GITHUB_REPOSITORY", "bibobo2266/AstraQuant")
    artifact_name = f"{cfg['storage']['artifact_prefix']}-{run_id}"
    manifest = {
        "name": cfg["name"],
        "formula_version": FORMULA_VERSION,
        "epoch": "E1",
        "period": [E1_START.date().isoformat(), E1_END.date().isoformat()],
        "warmup_start": warmup_start.date().isoformat(),
        "source_revision": SOURCE_REVISION,
        "config_path": str(CONFIG_PATH),
        "config_sha256": _sha256(CONFIG_PATH),
        "p2_060_exclusion_sha256": EXPECTED_EXCLUSION_SHA,
        "universe_config": cfg["universe"],
        "availability_policy": AVAILABILITY_POLICY,
        "total_return_benchmark": "FinMind TaiwanStockTotalReturnIndex:TAIEX",
        "stock_files": stock_files,
        "market_context": {
            "path": str(market_path),
            "size_bytes": market_path.stat().st_size,
            "sha256": _sha256(market_path),
            "rows": len(market_out),
        },
        "artifact_name": artifact_name,
        "workflow_run_id": run_id,
        "workflow_run_url": f"https://github.com/{repository}/actions/runs/{run_id}",
        "real_feature_keys": int(
            dictionary[dictionary["status"].eq("COMPLETE")]["feature_key"].nunique()
        ),
        "real_parameter_versions": int(dictionary["status"].eq("COMPLETE").sum()),
        "random_controls": int(dictionary["status"].eq("CONTROL").sum()),
        "blocked_data_features": blocked["column"].astype(str).tolist(),
        "available_at_audit_rows": len(audit),
        "available_at_violations": violations,
        "cache_hits": total_cache_hits,
        "cache_misses": total_cache_misses,
        "cache_repeat_hit_gate": bool(repeat_hit_gate),
        "runtime_seconds": runtime,
        "peak_rss_mb": peak_rss_mb,
        "no_effect_metrics": True,
        "round2_executed": False,
    }
    Path(cfg["storage"]["manifest"]).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    REPORT_PATH.write_text(
        _report(
            dictionary=dictionary,
            coverage=coverage,
            daily=daily,
            audit=audit,
            manifest=manifest,
        ),
        encoding="utf-8",
    )

    for path in PART_ROOT.glob("*.parquet"):
        path.unlink()
    try:
        PART_ROOT.rmdir()
    except OSError:
        pass

    print(
        json.dumps(
            {
                "real_feature_keys": manifest["real_feature_keys"],
                "real_parameter_versions": manifest["real_parameter_versions"],
                "random_controls": manifest["random_controls"],
                "blocked_data_features": manifest["blocked_data_features"],
                "available_at_violations": violations,
                "artifact_name": artifact_name,
                "runtime_seconds": runtime,
                "peak_rss_mb": peak_rss_mb,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


S1_VERSION = "trading-plan-r1-eligibility-v2"
S1_RS_INTERVALS = 250
S1_RS_REQUIRED_CLOSES = S1_RS_INTERVALS + 1
S1_FLAGS = ["liq_ok", "size_ok", "wk_trend_ok", "rs_ok", "rev_ok", "eps_ok", "eps_acc_ok", "excl_ok"]


def _s1_normalize(frame):
    out = frame.copy()
    out["date"] = pd.to_datetime(out["date"], errors="raise").dt.normalize()
    out["stock_id"] = out["stock_id"].astype(str)
    return out


def _s1_prepare(prices, tape):
    prices, tape = _s1_normalize(prices), _s1_normalize(tape)
    tape = tape[tape["stock_id"].str.fullmatch(r"[1-9]\d{3}")].copy()
    tape["market"] = tape["market"].astype(str).str.upper()
    official = tape[tape["market"].isin(["TWSE", "TPEX"]) & tape["observed_trade"].eq(True)]
    if official.empty:
        raise SystemExit("BLOCKED: no dated TWSE/TPEx official observations")
    calendar = pd.DatetimeIndex(sorted(official["date"].unique()), name="date")
    first = official.groupby("stock_id")["date"].min()
    keys = ["date", "stock_id"]
    if tape.duplicated(keys).any() or prices.duplicated(keys).any():
        raise SystemExit("BLOCKED: duplicate source price/tape keys")
    active = prices.merge(official[keys + ["market", "valid_ohlc"]],
                          on=keys, how="inner", validate="one_to_one").sort_values(keys).reset_index(drop=True)
    if active.empty:
        raise SystemExit("BLOCKED: no adjusted/official listed-stock matches")
    def matrix(field):
        return active.pivot(index="date", columns="stock_id", values=field).reindex(calendar)
    close = matrix("close")
    close = close.where(matrix("valid_ohlc").eq(True) & close.gt(0))
    return active, calendar, first, calendar.min(), close, matrix("Trading_Volume") / 1000, matrix("Trading_money")


def _s1_short_percentiles(ret120, full, short):
    donor = ret120.where(full).stack().rename("value").reset_index()
    donor["donor"] = 1
    target = ret120.where(short).stack().rename("value").reset_index()
    target["donor"] = 0
    empty = pd.DataFrame(np.nan, index=ret120.index, columns=ret120.columns)
    if target.empty or donor.empty:
        return empty
    counts = pd.concat([donor, target]).groupby(["date", "value"], as_index=False)["donor"].sum()
    counts = counts.sort_values(["date", "value"])
    counts["below"] = counts.groupby("date")["donor"].cumsum() - counts["donor"]
    counts["denominator"] = counts.groupby("date")["donor"].transform("sum")
    counts["score"] = 100 * (counts["below"] + counts["donor"] / 2) / counts["denominator"]
    ranked = target.merge(counts[["date", "value", "score"]], on=["date", "value"],
                          how="left", validate="many_to_one")
    return ranked.pivot(index="date", columns="stock_id", values="score").reindex(
        index=ret120.index, columns=ret120.columns)


def _s1_technical(prices, tape):
    active, calendar, first, origin, close, volume, amount = _s1_prepare(prices, tape)
    # Owner ruling: 250 return intervals require 251 complete closes.
    full = close.rolling(S1_RS_REQUIRED_CLOSES, min_periods=S1_RS_REQUIRED_CLOSES).count().eq(S1_RS_REQUIRED_CLOSES)
    valid120 = close.rolling(121, min_periods=121).count().eq(121)
    ret250 = (close / close.shift(S1_RS_INTERVALS) - 1).where(full)
    ret120 = (close / close.shift(120) - 1).where(valid120)
    first_position = calendar.get_indexer(first.reindex(close.columns))
    age = pd.DataFrame(np.arange(len(calendar))[:, None] - first_position[None, :],
                       index=calendar, columns=close.columns)
    short = age.ge(120) & age.lt(S1_RS_INTERVALS) & valid120 & first.reindex(close.columns).gt(origin)
    rs = (ret250.rank(axis=1, method="average", pct=True) * 100).where(
        ~short, _s1_short_percentiles(ret120, full, short))
    weekly = close.resample("W-FRI").last()
    ma6, ma20 = weekly.rolling(6, min_periods=6).mean(), weekly.rolling(20, min_periods=20).mean()
    # Shift the entire weekly input set. Never expose any current-week bar.
    weekly_inputs = {"wk_close": weekly.shift(1), "wk_ma6": ma6.shift(1),
                     "wk_ma20": ma20.shift(1), "wk_ma6_prev": ma6.shift(2), "wk_ma20_prev": ma20.shift(2)}
    date_idx, stock_idx = calendar.get_indexer(active["date"]), close.columns.get_indexer(active["stock_id"])
    def take(matrix):
        return matrix.to_numpy()[date_idx, stock_idx]
    out = active[["date", "stock_id"]].rename(columns={"stock_id": "stock"}).copy()
    out["volume5_lots"] = take(volume.rolling(5, min_periods=5).mean())
    out["size_proxy_turnover20_twd"] = take(amount.rolling(20, min_periods=20).mean())
    for name, matrix in weekly_inputs.items():
        daily = matrix.reindex(calendar.to_period("W-FRI").end_time.normalize())
        daily.index = calendar
        out[name] = take(daily)
    out["wk_available_date"] = out["date"].dt.to_period("W-FRI").dt.start_time - pd.Timedelta(days=1)
    out["return250"], out["return120"] = take(ret250), take(ret120)
    out["rs_denominator"] = full.sum(axis=1).reindex(out["date"]).to_numpy()
    out["rs"], out["rs_short"] = take(rs), take(short).astype(bool)
    out["liq_ok"], out["size_ok"] = out["volume5_lots"].ge(1000), out["size_proxy_turnover20_twd"].ge(50_000_000)
    out["wk_trend_ok"] = (
        out["wk_close"].gt(out["wk_ma6"]) & out["wk_ma6"].gt(out["wk_ma20"])
        & out["wk_ma6"].gt(out["wk_ma6_prev"]) & out["wk_ma20"].gt(out["wk_ma20_prev"]))
    out["rs_ok"] = out["rs"].ge(80)
    return out


def _s1_growth_events(frame, kind):
    frame = _s1_normalize(frame)
    frame["available_date"] = pd.to_datetime(frame["available_date"], errors="raise").dt.normalize()
    if frame["available_date"].isna().any() or frame["date"].isna().any():
        raise SystemExit("BLOCKED: missing fundamental available_date/period")
    if kind == "eps":
        frame = frame[frame["type"].eq("EPS")].copy()
        value_col, freq, lag = "value", "Q", 4
    else:
        value_col, freq, lag = "revenue", "M", 12
    if value_col not in frame or frame.empty:
        raise SystemExit(f"BLOCKED: missing/empty {kind} values")
    frame["period"] = frame["date"].dt.to_period(freq).astype("int64")
    frame["raw"] = pd.to_numeric(frame[value_col], errors="raise")
    if frame.duplicated(["stock_id", "period"]).any():
        raise SystemExit(f"BLOCKED: duplicate {kind} periods; no silent revision selection")
    base = frame[["stock_id", "period", "date", "available_date", "raw"]].copy()
    prior = base[["stock_id", "period", "available_date", "raw"]].copy()
    prior["period"] += lag
    prior = prior.rename(columns={"available_date": "prior_available_date", "raw": "prior_raw"})
    event = base.merge(prior, on=["stock_id", "period"], how="left", validate="one_to_one")
    event["yoy"] = 100 * (event["raw"] - event["prior_raw"]) / event["prior_raw"].abs().replace(0, np.nan)
    event["available_date"] = event[["available_date", "prior_available_date"]].max(axis=1)
    if kind == "eps":
        # Freeze the per-quarter YoY publication dates before joining previous quarters.
        yoy_events = event[["stock_id", "period", "available_date", "yoy"]].copy()
        for step in (1, 2):
            prev = yoy_events.copy()
            prev["period"] += step
            prev = prev.rename(columns={"yoy": f"yoy_prev{step}", "available_date": f"prev{step}_available_date"})
            event = event.merge(prev, on=["stock_id", "period"], how="left", validate="one_to_one")
        event["available_date"] = event[["available_date", "prev1_available_date", "prev2_available_date"]].max(axis=1)
    names = {"raw": f"{kind}_value", "prior_raw": f"{kind}_prior_year_value",
             "yoy": f"{kind}_yoy", "date": f"{kind}_period_date", "available_date": f"{kind}_available_date"}
    if kind == "eps":
        names.update({"yoy_prev1": "eps_yoy_prev1", "yoy_prev2": "eps_yoy_prev2"})
    return event[["stock_id", *names.keys()]].rename(columns=names)


def _s1_asof(panel, events, kind):
    events = events.rename(columns={"stock_id": "stock"})
    key = f"{kind}_available_date"
    events = events.sort_values([key, f"{kind}_period_date"]).drop_duplicates(["stock", key], keep="last")
    return pd.merge_asof(panel.sort_values("date"), events.sort_values(key), by="stock",
                         left_on="date", right_on=key, direction="backward", allow_exact_matches=True)


def _s1_panel(prices, tape, revenue, financials):
    out = _s1_technical(prices, tape)
    out = _s1_asof(out, _s1_growth_events(revenue, "rev"), "rev")
    out = _s1_asof(out, _s1_growth_events(financials, "eps"), "eps")
    out["rev_ok"], out["eps_ok"] = out["rev_yoy"].gt(20), out["eps_yoy"].gt(30)
    out["eps_acc_ok"] = out["eps_yoy"].gt(out["eps_yoy_prev1"]) & out["eps_yoy_prev1"].gt(out["eps_yoy_prev2"])
    out["excl_ok"] = True
    out["eligibility"] = out[S1_FLAGS].all(axis=1)
    out["source"], out["available_date"], out["rule_version"] = SOURCE_REVISION, out["date"], S1_VERSION
    return out.sort_values(["date", "stock"]).set_index(["date", "stock"])


def _s1_reference_fund(frame, stock, date, kind):
    source = _s1_normalize(frame)
    source["available_date"] = pd.to_datetime(source["available_date"]).dt.normalize()
    source = source[source["stock_id"].eq(stock) & source["available_date"].le(date)]
    if kind == "eps":
        source = source[source["type"].eq("EPS")]
        value, freq, lag = "value", "Q", 4
    else:
        value, freq, lag = "revenue", "M", 12
    names = [f"{kind}_value", f"{kind}_prior_year_value", f"{kind}_yoy",
             f"{kind}_period_date", f"{kind}_available_date"]
    if kind == "eps":
        names += ["eps_yoy_prev1", "eps_yoy_prev2"]
    if source.empty:
        return dict.fromkeys(names, np.nan)
    source["period"] = source["date"].dt.to_period(freq).astype("int64")
    source = source.sort_values(["date", "available_date"]).set_index("period")
    current, p = source.iloc[-1], source.index[-1]
    def growth(period):
        if period not in source.index or period-lag not in source.index:
            return np.nan
        now, prev = float(source.at[period, value]), float(source.at[period-lag, value])
        return 100 * (now-prev) / abs(prev) if prev != 0 else np.nan
    prior = float(source.at[p-lag, value]) if p-lag in source.index else np.nan
    used = [p, p-lag] + ([p-1, p-2, p-1-lag, p-2-lag] if kind == "eps" else [])
    available = source.loc[source.index.isin(used), "available_date"].max()
    result = dict(zip(names[:5], [float(current[value]), prior, growth(p), current["date"], available]))
    if kind == "eps":
        result.update(eps_yoy_prev1=growth(p-1), eps_yoy_prev2=growth(p-2))
    return result


def _s1_reference_technical(active, tape, date, stock):
    official = _s1_normalize(tape)
    official = official[official["stock_id"].str.fullmatch(r"[1-9]\d{3}")
                        & official["market"].astype(str).str.upper().isin(["TWSE", "TPEX"])
                        & official["observed_trade"].eq(True)]
    cal = pd.DatetimeIndex(sorted(official.loc[official["date"].le(date), "date"].unique()))
    history = active[active["date"].le(date)].copy()
    c = history.pivot(index="date", columns="stock_id", values="close").reindex(cal)
    valid = history.pivot(index="date", columns="stock_id", values="valid_ohlc").reindex(
        index=cal, columns=c.columns).eq(True)
    c = c.where(valid & c.gt(0))
    def returns(n):
        tail = c.tail(n+1)
        if len(tail) != n+1:
            return pd.Series(np.nan, index=c.columns)
        return (tail.iloc[-1] / tail.iloc[0]-1).where(tail.notna().all(axis=0))
    r250, r120 = returns(250), returns(120)
    donors = r250.dropna()
    first = official.loc[official["stock_id"].eq(stock), "date"].min()
    age = len(cal[cal >= first])-1
    short = bool(first > official["date"].min() and 120 <= age < 250 and pd.notna(r120.get(stock)))
    if short:
        group, x = r120.reindex(donors.index).dropna(), r120[stock]
        score = 100 * ((group < x).sum() + (group == x).sum()/2) / len(donors) if len(donors) else np.nan
    elif pd.notna(r250.get(stock)):
        x = r250[stock]
        score = 100 * ((donors < x).sum() + ((donors == x).sum()+1)/2) / len(donors)
    else:
        score = np.nan
    single = history[history["stock_id"].eq(stock)].set_index("date").reindex(cal)
    def mean(column, n, scale=1):
        values = single[column].tail(n)
        return values.mean()/scale if len(values) == n and values.notna().all() else np.nan
    weeks = c[stock].groupby(c.index.to_period("W-FRI")).last()
    # Keep every calendar week, including a whole-market holiday week.
    # Omitting an empty week silently extends the MA6/MA20 lookback.
    week_grid = pd.period_range(cal.min().to_period("W-FRI"), date.to_period("W-FRI"), freq="W-FRI")
    weeks = weeks.reindex(week_grid)
    weeks = weeks[weeks.index < date.to_period("W-FRI")]
    def weekly_mean(n, offset=0):
        values = weeks.iloc[:len(weeks)-offset] if offset else weeks
        values = values.tail(n)
        return values.mean() if len(values) == n and values.notna().all() else np.nan
    ref = dict(volume5_lots=mean("Trading_Volume", 5, 1000),
               size_proxy_turnover20_twd=mean("Trading_money", 20),
               wk_close=weeks.iloc[-1] if len(weeks) else np.nan,
               wk_ma6=weekly_mean(6), wk_ma20=weekly_mean(20),
               wk_ma6_prev=weekly_mean(6, 1), wk_ma20_prev=weekly_mean(20, 1),
               wk_available_date=date.to_period("W-FRI").start_time - pd.Timedelta(days=1),
               return250=r250.get(stock, np.nan), return120=r120.get(stock, np.nan),
               rs_denominator=len(donors), rs=score, rs_short=short)
    ref.update(liq_ok=ref["volume5_lots"] >= 1000, size_ok=ref["size_proxy_turnover20_twd"] >= 50_000_000,
               rs_ok=score >= 80, wk_trend_ok=(ref["wk_close"] > ref["wk_ma6"] > ref["wk_ma20"]
               and ref["wk_ma6"] > ref["wk_ma6_prev"] and ref["wk_ma20"] > ref["wk_ma20_prev"]))
    return ref


def _s1_audit(panel, prices, tape, revenue, financials):
    # Only these ten source comparisons; no full-population audit.
    if len(panel) < 10:
        raise SystemExit("BLOCKED: fewer than ten panel rows")
    sample = panel.sample(n=10, random_state=20261008).sort_index()
    active, *_ = _s1_prepare(prices, tape)
    checks, summaries = [], []
    for (date, stock), row in sample.iterrows():
        ref = _s1_reference_technical(active, tape, date, stock)
        ref.update(_s1_reference_fund(revenue, stock, date, "rev"))
        ref.update(_s1_reference_fund(financials, stock, date, "eps"))
        ref.update(rev_ok=ref["rev_yoy"] > 20, eps_ok=ref["eps_yoy"] > 30,
                   eps_acc_ok=ref["eps_yoy"] > ref["eps_yoy_prev1"] > ref["eps_yoy_prev2"],
                   excl_ok=True, source=SOURCE_REVISION, available_date=date, rule_version=S1_VERSION)
        ref["eligibility"] = all(ref[key] for key in S1_FLAGS)
        matched = 0
        for field in panel.columns:
            actual, expected = row[field], ref[field]
            if pd.isna(actual) and pd.isna(expected):
                ok = True
            elif isinstance(actual, (float, np.floating)) and isinstance(expected, (int, float, np.number)):
                ok = bool(np.isclose(actual, expected, rtol=1e-10, atol=1e-8, equal_nan=True))
            else:
                ok = bool(actual == expected) if pd.notna(actual) and pd.notna(expected) else False
            matched += int(ok)
            checks.append(dict(date=date, stock=stock, field=field, actual=actual, source_value=expected, match=ok))
        summaries.append(dict(date=date, stock=stock, fields=len(panel.columns), matched=matched,
                              result="PASS" if matched == len(panel.columns) else "FAIL"))
    return pd.DataFrame(checks), pd.DataFrame(summaries), sample


def _s1_main():
    if not SOURCE_REVISION:
        raise SystemExit("BLOCKED: SOURCE_REVISION is required")
    cfg, _ = _load_cfg()
    settings = cfg["eligibility_panel"]
    prices = _load_adjusted(pd.Timestamp(cfg["warmup_start"]))
    paths = dict(tape=SOURCE_ROOT / "reference/tradability.parquet",
                 revenue=SOURCE_ROOT / "fundamentals/month_revenue.parquet",
                 financials=SOURCE_ROOT / "fundamentals/financials.parquet")
    for name, path in paths.items():
        if not path.exists():
            raise SystemExit(f"BLOCKED: missing {name} runtime source {path}")
    tape = pd.read_parquet(paths["tape"], columns=["date", "stock_id", "market", "observed_trade", "valid_ohlc"])
    tape = _s1_normalize(tape)
    tape = tape[tape["date"].le(E1_END)]
    revenue, financials = pd.read_parquet(paths["revenue"]), pd.read_parquet(paths["financials"])
    for name, frame in [("revenue", revenue), ("financials", financials)]:
        if {"date", "stock_id", "available_date"} - set(frame):
            raise SystemExit(f"BLOCKED: {name} missing PIT keys")
    if "revenue" not in revenue or {"type", "value"} - set(financials):
        raise SystemExit("BLOCKED: runtime missing revenue/EPS value columns")
    revenue = revenue[pd.to_datetime(revenue["available_date"]).le(E1_END)].copy()
    financials = financials[pd.to_datetime(financials["available_date"]).le(E1_END)].copy()
    panel = _s1_panel(prices, tape, revenue, financials)
    dates = panel.index.get_level_values("date")
    panel = panel[(dates >= E1_START) & (dates <= E1_END)]
    dates = panel.index.get_level_values("date")
    checks, summary, sample = _s1_audit(panel, prices, tape, revenue, financials)
    Path("out").mkdir(exist_ok=True)
    checks.to_csv(settings["checks"], index=False)
    summary.to_csv(settings["sample_results"], index=False)
    sample.to_csv(settings["samples"])
    if not summary["result"].eq("PASS").all():
        failures = checks[~checks["match"]][["date", "stock", "field"]].to_dict("records")
        raise SystemExit("BLOCKED: ten-row comparison failed " + json.dumps(failures, default=str))
    target = Path(settings["path"])
    target.parent.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(target, index=True, compression="zstd")
    manifest = dict(rows=len(panel), date_start=str(dates.min().date()), date_end=str(dates.max().date()),
                    source_revision=SOURCE_REVISION, rule_version=S1_VERSION, epoch="E1",
                    no_effect_metrics=True, exclusion_skipped=True, sample_pass=10,
                    path=str(target), panel_sha256=_sha256(target),
                    source_paths={key: str(path.relative_to(SOURCE_ROOT)) for key, path in paths.items()},
                    field_notes=settings["field_notes"])
    Path(settings["manifest"]).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print("S1_REPORT 檔案：data/panel/eligibility_panel.parquet（Actions artifact）")
    print(f"S1_REPORT 列數：{len(panel):,}；日期：{manifest['date_start']}～{manifest['date_end']}；抽驗 10/10 PASS。")
    print("S1_REPORT 每筆每欄均已對原始來源；逐欄 actual/source_value CSV 隨 artifact 保存。")
    print("S1_REPORT | date | stock | 原始值對照：量／額／RS／營收YoY／EPSYoY | 每欄核對 |")
    print("S1_REPORT |---|---|---|---|")
    for (_, r), ((_, _), v) in zip(summary.iterrows(), sample.iterrows()):
        fields = ["volume5_lots", "size_proxy_turnover20_twd", "rs", "rev_yoy", "eps_yoy"]
        values = "/".join("NA" if pd.isna(v[f]) else f"{v[f]:.6g}" for f in fields)
        print(f"S1_REPORT | {r['date'].date()} | {r['stock']} | {values}（均=來源） | {r['matched']}/{r['fields']} PASS |")
    print("S1_REPORT 註：excl_ok=True，跳過產業排除；rs_short 用首次官方行情日，資料起點已存在者不算新上市。")
    print("S1_REPORT 基本面可用日沿用 runtime 的保守估計，並非原始公告／修訂版本證明。")


if __name__ == "__main__":
    if os.environ.get("BUILD_ELIGIBILITY_PANEL") == "1":
        _s1_main()
    else:
        main()
