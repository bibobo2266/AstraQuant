from __future__ import annotations

import hashlib
import json
import math
from itertools import combinations
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


NULL_CALIBRATION_TEXT = (
    "亂數對照／預期偽陽性數尚未完成，本輪無推論性存活名單"
)
OVERLAP_WARNING = (
    "參數組合的主要贏家重疊，需檢查高原是否依賴共同個股／行情"
)


def normalized_frame_hash(frame: pd.DataFrame) -> str:
    if frame.empty:
        return hashlib.sha256(b"EMPTY").hexdigest()
    work = frame.copy().reindex(sorted(frame.columns), axis=1)
    sort_cols = [
        c
        for c in ("config_id", "trade_id", "stock_id", "signal_date", "entry_date")
        if c in work.columns
    ]
    if sort_cols:
        work = work.sort_values(sort_cols, kind="stable")
    raw = work.to_csv(index=False, na_rep="<NA>", float_format="%.15g")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def closed_metrics(trades: pd.DataFrame) -> dict[str, object]:
    if trades.empty:
        return {
            "n_closed": 0,
            "win_rate": np.nan,
            "loss_rate": np.nan,
            "breakeven_rate": np.nan,
            "avg_win": np.nan,
            "avg_loss": np.nan,
            "payoff": np.nan,
            "expectancy": np.nan,
        }
    r = pd.to_numeric(trades["net_return"], errors="coerce")
    if r.isna().any():
        raise ValueError("closed trade contains invalid net_return")
    wins = r[r > 0]
    losses = r[r < 0]
    flat = r[r == 0]
    avg_win = float(wins.mean()) if len(wins) else np.nan
    avg_loss = float((-losses).mean()) if len(losses) else np.nan
    payoff = (
        avg_win / avg_loss
        if len(wins) and len(losses) and avg_loss > 0
        else np.nan
    )
    expectancy = float(r.mean())
    win_rate = float(len(wins) / len(r))
    loss_rate = float(len(losses) / len(r))
    breakeven_rate = float(len(flat) / len(r))
    identity = (
        (0.0 if math.isnan(avg_win) else win_rate * avg_win)
        - (0.0 if math.isnan(avg_loss) else loss_rate * avg_loss)
    )
    if not math.isclose(expectancy, identity, rel_tol=1e-11, abs_tol=1e-13):
        raise ValueError(
            f"expectancy identity failed: direct={expectancy} identity={identity}"
        )
    return {
        "n_closed": int(len(r)),
        "win_rate": win_rate,
        "loss_rate": loss_rate,
        "breakeven_rate": breakeven_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "payoff": payoff,
        "expectancy": expectancy,
    }


def expectancy_without_top(
    trades: pd.DataFrame,
    n: int,
) -> tuple[float, int]:
    if trades.empty or len(trades) <= n:
        return np.nan, 0
    values = pd.to_numeric(
        trades["net_return"], errors="raise"
    ).sort_values(ascending=False, kind="stable")
    kept = values.iloc[n:]
    return float(kept.mean()), int(len(kept))


def summary_row(
    *,
    config_id: str,
    params: dict[str, object],
    simulation,
    low_n_threshold: int,
) -> dict[str, object]:
    metrics = closed_metrics(simulation.trades)
    entry_frames = []
    if not simulation.trades.empty:
        entry_frames.append(
            simulation.trades[["stock_id", "entry_date"]].copy()
        )
    if not simulation.open_positions.empty:
        entry_frames.append(
            simulation.open_positions[["stock_id", "entry_date"]].copy()
        )
    entries = (
        pd.concat(entry_frames, ignore_index=True)
        if entry_frames
        else pd.DataFrame(columns=["stock_id", "entry_date"])
    )
    row = {
        "config_id": config_id,
        "base_len": int(params["trigger.base_len"]),
        "last_contraction": float(params["trigger.last_contraction"]),
        "dry_up": float(params["trigger.dry_up"]),
        "breakout_vol": float(params["trigger.breakout_vol"]),
        "signal_count": int(simulation.signal_count),
        "entry_count": int(simulation.entry_count),
        **metrics,
        "n_open": int(len(simulation.open_positions)),
        "ignored_while_holding": int(simulation.ignored_while_holding),
        "chase_reject_count": int(simulation.chase_reject_count),
        "other_unfilled_count": int(simulation.other_unfilled_count),
        "unique_stocks": int(entries["stock_id"].nunique()) if len(entries) else 0,
        "entry_date_count": int(entries["entry_date"].nunique()) if len(entries) else 0,
        "unverified_terminal_trade_count": int(
            simulation.unverified_terminal_trade_count
        ),
        "low_n": bool(int(metrics["n_closed"]) < low_n_threshold),
    }
    for n in (1, 3, 5):
        value, remaining = expectancy_without_top(simulation.trades, n)
        row[f"expectancy_ex_top{n}"] = value
        row[f"n_closed_ex_top{n}"] = remaining
    return row


def _plot_axis_summary(
    results: pd.DataFrame,
    *,
    column: str,
    values: list[object],
    path: Path,
    cost_text: str,
) -> None:
    usable = results[
        ~results["low_n"].astype(bool)
        & pd.to_numeric(results["expectancy"], errors="coerce").notna()
    ].copy()
    med, q1, q3, trades, counts = [], [], [], [], []
    for value in values:
        group = usable[usable[column].eq(value)]
        x = pd.to_numeric(group["expectancy"], errors="coerce").dropna()
        med.append(float(x.median()) if len(x) else np.nan)
        q1.append(float(x.quantile(0.25)) if len(x) else np.nan)
        q3.append(float(x.quantile(0.75)) if len(x) else np.nan)
        trades.append(
            float(pd.to_numeric(group["n_closed"], errors="coerce").median())
            if len(group)
            else np.nan
        )
        counts.append(int(len(group)))

    positions = np.arange(len(values))
    fig, ax = plt.subplots(figsize=(9, 5.5))
    med_arr = np.asarray(med, dtype=float)
    q1_arr = np.asarray(q1, dtype=float)
    q3_arr = np.asarray(q3, dtype=float)
    err = np.vstack([med_arr - q1_arr, q3_arr - med_arr])
    ax.errorbar(
        positions,
        med_arr * 100,
        yerr=err * 100,
        marker="o",
        capsize=5,
    )
    ax.axhline(0, linewidth=0.8)
    ax.set_xticks(positions, [str(v) for v in values])
    ax.set_xlabel(column)
    ax.set_ylabel("其他組合 expectancy 中位數與 IQR (%)")
    ax2 = ax.twinx()
    ax2.plot(positions, trades, marker="s")
    ax2.set_ylabel("有效 config 的 n_closed 中位數")
    ax.set_title(
        f"VCP Round 1 — {column} 單軸聚合\n"
        "E1 2016-01-04~2021-12-31；排除 low_n config"
    )
    fig.text(
        0.01,
        0.01,
        f"聚合：其他三軸中位數/IQR；成本：{cost_text}；"
        f"單位：expectancy=%；有效 config={len(usable)}；"
        f"各值有效數={counts}",
        fontsize=8,
    )
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _plot_heatmap(
    results: pd.DataFrame,
    *,
    xcol: str,
    ycol: str,
    xvalues: list[object],
    yvalues: list[object],
    path: Path,
    cost_text: str,
) -> None:
    usable = results[
        ~results["low_n"].astype(bool)
        & pd.to_numeric(results["expectancy"], errors="coerce").notna()
    ].copy()
    matrix = np.full((len(yvalues), len(xvalues)), np.nan, dtype=float)
    nmatrix = np.zeros((len(yvalues), len(xvalues)), dtype=int)
    for iy, yv in enumerate(yvalues):
        for ix, xv in enumerate(xvalues):
            group = usable[usable[xcol].eq(xv) & usable[ycol].eq(yv)]
            vals = pd.to_numeric(
                group["expectancy"], errors="coerce"
            ).dropna()
            if len(vals):
                matrix[iy, ix] = float(vals.median()) * 100
                nmatrix[iy, ix] = int(len(vals))

    fig, ax = plt.subplots(figsize=(8, 6))
    masked = np.ma.masked_invalid(matrix)
    image = ax.imshow(masked, aspect="auto")
    ax.set_xticks(range(len(xvalues)), [str(v) for v in xvalues])
    ax.set_yticks(range(len(yvalues)), [str(v) for v in yvalues])
    ax.set_xlabel(xcol)
    ax.set_ylabel(ycol)
    ax.set_title(
        f"VCP Round 1 — {xcol} × {ycol}\n"
        "其餘兩軸 expectancy 中位數；E1；low_n 不進色階"
    )
    for iy in range(len(yvalues)):
        for ix in range(len(xvalues)):
            if math.isfinite(matrix[iy, ix]):
                ax.text(
                    ix,
                    iy,
                    f"{matrix[iy, ix]:.2f}%\nn={nmatrix[iy, ix]}",
                    ha="center",
                    va="center",
                    fontsize=8,
                )
    fig.colorbar(image, ax=ax, label="median expectancy (%)")
    fig.text(
        0.01,
        0.01,
        f"聚合：其餘兩軸中位數；成本：{cost_text}；"
        f"單位：expectancy=%；有效 config={len(usable)}；不內插未測格點。",
        fontsize=8,
    )
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(path, dpi=160)
    plt.close(fig)


def make_charts(
    results: pd.DataFrame,
    *,
    out_dir: Path,
    cost_text: str,
    axis_values: dict[str, list[object]],
) -> list[str]:
    chart_paths: list[str] = []
    for column, values in axis_values.items():
        path = out_dir / f"vcp_round1_axis_{column}.png"
        _plot_axis_summary(
            results,
            column=column,
            values=values,
            path=path,
            cost_text=cost_text,
        )
        chart_paths.append(path.as_posix())

    for xcol, ycol in combinations(axis_values, 2):
        path = out_dir / f"vcp_round1_heatmap_{xcol}_x_{ycol}.png"
        _plot_heatmap(
            results,
            xcol=xcol,
            ycol=ycol,
            xvalues=axis_values[xcol],
            yvalues=axis_values[ycol],
            path=path,
            cost_text=cost_text,
        )
        chart_paths.append(path.as_posix())
    if len(chart_paths) != 10:
        raise RuntimeError("expected exactly 10 VCP round1 charts")
    return chart_paths


def _jaccard(a: set, b: set) -> tuple[int, int, int, float]:
    union = a | b
    inter = a & b
    return len(a), len(b), len(inter), (
        float(len(inter) / len(union)) if union else np.nan
    )


def overlap_table(
    *,
    results: pd.DataFrame,
    trades: pd.DataFrame,
    high_score_fraction: float,
    overlap_top_trades: int,
    overlap_warning_threshold: float,
) -> tuple[pd.DataFrame, int, int]:
    valid = results[
        pd.to_numeric(results["expectancy"], errors="coerce").notna()
        & results["n_closed"].gt(0)
    ].sort_values(["expectancy", "config_id"], ascending=[False, True])
    high_n = (
        int(math.ceil(len(valid) * high_score_fraction))
        if len(valid)
        else 0
    )
    high_ids = set(valid.head(high_n)["config_id"].astype(str))

    top_sets: dict[str, tuple[set[str], set[tuple[str, str]], int]] = {}
    for config_id in results["config_id"].astype(str):
        group = trades[
            trades["config_id"].astype(str).eq(config_id)
        ].copy()
        group = group.sort_values(
            ["net_return", "trade_id"],
            ascending=[False, True],
            kind="stable",
        ).head(overlap_top_trades)
        top_sets[config_id] = (
            set(group["stock_id"].astype(str)),
            set(
                zip(
                    group["stock_id"].astype(str),
                    group["entry_date"].astype(str),
                )
            ),
            int(len(group)),
        )

    rows: list[dict[str, object]] = []
    warning_count = 0
    ids = list(results["config_id"].astype(str))
    for a, b in combinations(ids, 2):
        sa, da, na = top_sets[a]
        sb, db, nb = top_sets[b]
        asz, bsz, sint, sj = _jaccard(sa, sb)
        adz, bdz, dint, dj = _jaccard(da, db)
        warn = bool(
            a in high_ids
            and b in high_ids
            and (
                (math.isfinite(sj) and sj > overlap_warning_threshold)
                or (math.isfinite(dj) and dj > overlap_warning_threshold)
            )
        )
        warning_count += int(warn)
        rows.append(
            {
                "record_type": "PAIR",
                "config_id": "",
                "config_a": a,
                "config_b": b,
                "config_a_high_score": a in high_ids,
                "config_b_high_score": b in high_ids,
                "top_trade_count_a": na,
                "top_trade_count_b": nb,
                "stock_set_size_a": asz,
                "stock_set_size_b": bsz,
                "stock_intersection": sint,
                "stock_jaccard": sj,
                "stock_entry_set_size_a": adz,
                "stock_entry_set_size_b": bdz,
                "stock_entry_intersection": dint,
                "stock_entry_jaccard": dj,
                "overlap_warning": OVERLAP_WARNING if warn else "",
                "high_score_config_count": high_n,
                "expectancy": np.nan,
                "expectancy_ex_top1": np.nan,
                "expectancy_ex_top3": np.nan,
                "expectancy_ex_top5": np.nan,
                "n_closed": np.nan,
                "n_closed_ex_top1": np.nan,
                "n_closed_ex_top3": np.nan,
                "n_closed_ex_top5": np.nan,
            }
        )

    for row in results.itertuples(index=False):
        rows.append(
            {
                "record_type": "SENSITIVITY",
                "config_id": row.config_id,
                "config_a": "",
                "config_b": "",
                "config_a_high_score": row.config_id in high_ids,
                "config_b_high_score": False,
                "top_trade_count_a": top_sets[row.config_id][2],
                "top_trade_count_b": np.nan,
                "stock_set_size_a": np.nan,
                "stock_set_size_b": np.nan,
                "stock_intersection": np.nan,
                "stock_jaccard": np.nan,
                "stock_entry_set_size_a": np.nan,
                "stock_entry_set_size_b": np.nan,
                "stock_entry_intersection": np.nan,
                "stock_entry_jaccard": np.nan,
                "overlap_warning": "",
                "high_score_config_count": high_n,
                "expectancy": row.expectancy,
                "expectancy_ex_top1": row.expectancy_ex_top1,
                "expectancy_ex_top3": row.expectancy_ex_top3,
                "expectancy_ex_top5": row.expectancy_ex_top5,
                "n_closed": row.n_closed,
                "n_closed_ex_top1": row.n_closed_ex_top1,
                "n_closed_ex_top3": row.n_closed_ex_top3,
                "n_closed_ex_top5": row.n_closed_ex_top5,
            }
        )
    return pd.DataFrame(rows), high_n, warning_count


def _marginal_table(results: pd.DataFrame, column: str) -> list[str]:
    lines = [
        f"### {column}",
        "",
        "| 值 | 有效 config | expectancy 中位數 | Q1 | Q3 | n_closed 中位數 |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    usable = results[
        ~results["low_n"].astype(bool)
        & pd.to_numeric(results["expectancy"], errors="coerce").notna()
    ]
    for value, group in usable.groupby(column, sort=True):
        x = pd.to_numeric(group["expectancy"], errors="coerce").dropna()
        lines.append(
            f"| {value} | {len(group)} | {x.median()*100:.3f}% "
            f"| {x.quantile(.25)*100:.3f}% | {x.quantile(.75)*100:.3f}% "
            f"| {pd.to_numeric(group['n_closed']).median():.0f} |"
        )
    if len(lines) == 4:
        lines.append("| — | 0 | — | — | — | — |")
    lines.append("")
    return lines


def write_report(
    *,
    report_path: Path,
    summary_path: Path,
    trades_path: Path,
    open_path: Path,
    overlap_path: Path,
    pilot_path: Path,
    diagnostics_path: Path,
    manifest_path: Path,
    results: pd.DataFrame,
    source_revision: str,
    code_revision: str,
    config_hashes: dict[str, str],
    p2_sha: str,
    eligible_count: int,
    p2_excluded_count: int,
    liquidity_threshold: float,
    terminal_unverified_count: int,
    terminal_affected_count: int,
    high_score_count: int,
    warning_count: int,
    pilot_count: int,
    pilot_seconds: float,
    full_seconds: float,
    cache_hits: int,
    cache_misses: int,
    chart_paths: list[str],
    low_n_threshold: int,
) -> None:
    valid = results[pd.to_numeric(results["expectancy"], errors="coerce").notna()]
    usable = valid[~valid["low_n"].astype(bool)]
    cost_text = (
        "買0.1425%手續費；賣0.1425%手續費+0.3%證交稅；"
        "買賣各0.1%不利滑價"
    )
    lines = [
        "# VCP Round 1：三段收縮完整進出場掃描",
        "",
        "狀態：COMPLETE（E1 描述性研究）",
        "",
        "## 結論邊界",
        "",
        "- 本輪是 TRANSLATED 研究假設，不冒充老手原始 VCP 的完整裁量定義。",
        "- 不宣告最佳策略、不宣告顯著、不宣告可出售或可實盤；不 promote、不解鎖 OOS。",
        "- E1 只到 2021-12-31；期末未平倉不強制出場，也未讀取 E2 價格補完。",
        f"- {NULL_CALIBRATION_TEXT}。既有 placebo 使用不同訊號、共享資金、零摩擦與固定停損/時間出場，不能依原凍結契約直接移植到本輪。",
        "- 多重檢定校正與跨時期穩定性尚未完成；圖上的連續區域只能稱候選高原。",
        "",
        "## Run identity",
        "",
        "- strategy version: vcp_round1_three_segment_v1",
        "- epoch: E1：歷史開發期（2016-01-04～2021-12-31）",
        f"- source revision: {source_revision}",
        f"- code commit: {code_revision}",
        f"- P2-060 exclusion SHA: {p2_sha}",
        f"- top-25%-turnover eligibility union distinct tickers: {eligible_count}；不是無條件全市場。",
        f"- P2-060 排除清冊 distinct tickers: {p2_excluded_count}。",
        "- all_liquid 實際條件：四碼、close>=10、observed_trade、valid_ohlc、P2-060 排除、同日成交額 top 25%。",
        f"- 額外訊號流動性條件：訊號日前 20 日平均成交額 >= TWD {liquidity_threshold:,.0f}。",
        f"- 成本：{cost_text}。",
        "- 指標／pivot：一致 CA 的 adjusted research coordinate；成交與現金損益：RAW execution + canonical CA accounting。",
        f"- config hashes: {json.dumps(config_hashes, ensure_ascii=False, sort_keys=True)}",
        f"- pilot configs / runtime: {pilot_count} / {pilot_seconds:.2f}s",
        f"- full configs / runtime: {len(results)} / {full_seconds:.2f}s",
        f"- feature cache hits / misses: {cache_hits} / {cache_misses}",
        "",
        "## 掃描完整性",
        "",
        f"- 108 格：{len(results)}；缺格：{108-len(results)}。",
        f"- 有已平倉交易的 config：{len(valid)}。",
        f"- n_closed >= {low_n_threshold}、可進高原圖色階的 config：{len(usable)}。",
        f"- 全部 signal_count：{int(results['signal_count'].sum())}；entry_count：{int(results['entry_count'].sum())}。",
        f"- 全部 n_closed：{int(results['n_closed'].sum())}；n_open：{int(results['n_open'].sum())}。",
        f"- 追價拒絕：{int(results['chase_reject_count'].sum())}；其他未成交：{int(results['other_unfilled_count'].sum())}。",
        "- 已平倉統計受 E1 期末未平倉截尾影響；open positions 不混入 win/loss/payoff/expectancy。",
        "",
        "## 哪些參數區域看起來較穩定？",
        "",
        "本輪不事後新增高原通過門檻。以下只列各軸對其他三軸聚合後的 expectancy 中位數與 IQR；相鄰數值是否連續需與六張雙軸圖及 108 原始格共同閱讀，不能把單一最高格當成結論。",
        "",
    ]
    for col in ("base_len", "last_contraction", "dry_up", "breakout_vol"):
        lines += _marginal_table(results, col)

    entry_rates = results["entry_count"] / results["signal_count"].replace(0, np.nan)
    lines += [
        "## 交易機會與代價如何變化？",
        "",
        f"- config signal_count 範圍：{int(results['signal_count'].min())}～{int(results['signal_count'].max())}。",
        f"- config entry_count 範圍：{int(results['entry_count'].min())}～{int(results['entry_count'].max())}。",
        (
            f"- 訊號到實際進場比例中位數：{entry_rates.median()*100:.2f}%"
            if entry_rates.notna().any()
            else "- 訊號到實際進場比例中位數：無"
        ),
        "- 每筆均以相同初始名目資金正規化；不同股價不改變交易統計權重。",
        "- 主要執行摩擦直接體現在追價拒絕、其他未成交、成本後 net_return 與 blocked exit attempts；不另在報告層重扣成本。",
        "",
        "## 是否主要依賴少數個股或交易？",
        "",
        f"- expectancy 前 25% 的有效 config 數：{high_score_count}。",
        f"- 高分組 pair 中觸發 >60% 贏家重疊警示的組數：{warning_count}。",
        "- overlap 檔保留股票集合與（股票、進場日）集合 Jaccard，以及各 config 移除前 1/3/5 大獲利交易後 expectancy。",
        (
            f"- {OVERLAP_WARNING}。"
            if warning_count
            else "- 本輪高分組 pair 未觸發 >60% 的指定重疊警示；這不等於已證明不存在共同行情依賴。"
        ),
        "",
        "## 下市／終止生命週期",
        "",
        f"- E1 母體中由現行 canonical fallback 建模、外部終止事實仍未確認的 terminal ticker 數：{terminal_unverified_count}。",
        f"- 受 UNVERIFIED_TERMINAL_CASHOUT 影響的已進場交易／未平倉記錄數（跨 config 計）：{terminal_affected_count}。",
        "- 這些交易保留並單獨標示；沒有只跑現存股票清單。",
        "",
        "## 哪些結論仍無法成立？",
        "",
        "- 無法成立：統計顯著性、預期偽陽性存活名單、多重檢定校正後優勢、E2 跨時期穩定性、E3 效果、獨立 OOS、可實盤／可出售判定。",
        "- 無法把本輪三段收縮、ATR21×2.5 或 D21 說成老手唯一原始定義。",
        "- 無法把候選高原視為已確認優勢；第二輪若改定義必須新增實驗版本與搜尋紀錄。",
        "",
        "## 產物",
        "",
        f"- {summary_path.as_posix()} — 108 格完整總表。",
        f"- {trades_path.as_posix()} — 成本後逐筆已平倉交易。",
        f"- {open_path.as_posix()} — E1 期末未平倉。",
        f"- {overlap_path.as_posix()} — top-20 overlap 與移除最大獲利敏感度。",
        f"- {pilot_path.as_posix()} — 先行 {pilot_count}-config 驗證紀錄。",
        f"- {diagnostics_path.as_posix()} — 候選判定與未成交原因彙總。",
        f"- {manifest_path.as_posix()} — source/config/code/cost/run manifest。",
        "",
        "### 圖",
        "",
    ]
    lines += [f"- {path}" for path in chart_paths]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
