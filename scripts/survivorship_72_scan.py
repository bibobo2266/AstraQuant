"""AQ-EXP-SURVIVOR-001 — 未建模下市股與 E1 母體的接觸面清點。

純 membership accounting：只數「這些股票在不在母體內、在多久」，
不執行策略觸發、不計算任何報酬，因此不觸及 FORMAL_RESEARCH gate。

公開 ticker 清單與最後 RAW 日取自 repo 內既有的
docs/SOURCE_TERMINAL_COVERAGE_AUDIT.md。
母體成員資格取自私有逐列證據，透過環境變數指定路徑；
本腳本只輸出聚合，不複製任何逐列內容到本 repo。

    AQ_COVERAGE_ROWS=/path/aq_exp_data_001_eligibility_reason_rows.parquet \
        python3 scripts/survivorship_72_scan.py

無該環境變數時只輸出公開部分並明示未完成，不偽裝已執行。
"""
import json
import os
import re
import sys

import pandas as pd

AUDIT = "docs/SOURCE_TERMINAL_COVERAGE_AUDIT.md"
OUT = "out/survivorship_e1_universe_contact.json"
E1_START = pd.Timestamp("2016-01-04")
# manifest 宣告的期末。母體實際最後一列可能早於它（當日無合格列），
# 所以 E1_END 一律從資料推導，只用宣告值當上界檢查。
MANIFEST_PERIOD_END = pd.Timestamp("2021-12-31")
RISK_GAP_DAYS = 30        # 退出母體到最後交易日在此天數內＝下市時仍可能持有
BUCKETS = [(0, 5), (6, 30), (31, 120), (121, 10 ** 9)]


def unmodeled_tickers(path: str = AUDIT) -> pd.DataFrame:
    """從既有稽核文件取未建模下市股清單（ticker + 最後 RAW 日）。"""
    txt = open(path, encoding="utf-8").read()
    sec = txt.split("## Unmodeled terminal securities")[1].split("\n## ")[0]
    rows = re.findall(r"^\|\s*(\d{4})\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|", sec, re.M)
    df = pd.DataFrame(rows, columns=["stock_id", "last_raw"])
    df["last_raw"] = pd.to_datetime(df["last_raw"])
    return df


def contact(rows_path: str, un: pd.DataFrame):
    rows = pd.read_parquet(rows_path, columns=["date", "stock_id"])
    rows["stock_id"] = rows["stock_id"].astype(str)
    e1_end = rows["date"].max()
    if e1_end > MANIFEST_PERIOD_END:
        raise ValueError(
            f"母體最後一列 {e1_end:%Y-%m-%d} 超出 manifest 宣告的期末 "
            f"{MANIFEST_PERIOD_END:%Y-%m-%d}；母體可能換了版本，先停下來對帳。")
    g = rows.groupby("stock_id")["date"].agg(["min", "max", "count"])

    h = un.join(g, on="stock_id")
    h["in_universe"] = h["count"].notna()
    h["ends_in_e1"] = h["last_raw"].between(E1_START, e1_end)
    # 退出母體到最後一個 RAW 交易日的間隔。0 代表下市當天還在母體裡。
    h["exit_gap_days"] = (h["last_raw"] - h["max"]).dt.days

    live = h[h["in_universe"] & h["ends_in_e1"]]
    risky = live[live["exit_gap_days"] <= RISK_GAP_DAYS]

    # 風險窗內的股票日：最後 RAW 交易日前 RISK_GAP_DAYS 天內，實際在母體裡的天數。
    # 這跟「這些 ticker 一輩子在母體裡的天數」是兩回事，不可混用。
    win = 0
    for sid, lr in zip(risky["stock_id"], risky["last_raw"]):
        sub = rows[(rows.stock_id == sid)
                   & (rows.date > lr - pd.Timedelta(days=RISK_GAP_DAYS))
                   & (rows.date <= lr)]
        win += len(sub)

    res = {
        "universe_rows": int(len(rows)),
        "universe_stocks": int(rows["stock_id"].nunique()),
        "unmodeled_total": int(len(un)),
        "ever_in_universe": int(h["in_universe"].sum()),
        "never_in_universe": sorted(h.loc[~h["in_universe"], "stock_id"]),
        "ever_in_universe_stock_days": int(h["count"].sum()),
        "ends_in_e1": int(h["ends_in_e1"].sum()),
        "ends_in_e1_and_in_universe": int(len(live)),
        "exit_gap_buckets": {
            f"{lo}-{hi}": {
                "tickers": int(((live.exit_gap_days >= lo)
                                & (live.exit_gap_days <= hi)).sum()),
                "stock_days": int(live.loc[(live.exit_gap_days >= lo)
                                           & (live.exit_gap_days <= hi),
                                           "count"].sum()),
            } for lo, hi in BUCKETS},
        "at_risk_tickers": sorted(risky["stock_id"]),
        # 這 21 檔在母體裡的「全部」股票日，不是風險窗內的天數
        "at_risk_ticker_lifetime_universe_days": int(risky["count"].sum()),
        "days_within_30d_of_last_raw": int(win),
        "e1_end_observed": e1_end.strftime("%Y-%m-%d"),
        "manifest_period_end": MANIFEST_PERIOD_END.strftime("%Y-%m-%d"),
    }
    res["at_risk_lifetime_share_pct"] = round(
        res["at_risk_ticker_lifetime_universe_days"] / res["universe_rows"] * 100, 3)
    res["risk_window_share_pct"] = round(win / res["universe_rows"] * 100, 3)
    return res, h


def main():
    un = unmodeled_tickers()
    path = os.environ.get("AQ_COVERAGE_ROWS", "")
    if not path or not os.path.exists(path):
        print(f"未提供 AQ_COVERAGE_ROWS，僅取得公開清單 {len(un)} 檔；"
              "接觸面未計算。", file=sys.stderr)
        return 1
    res, _ = contact(path, un)
    os.makedirs("out", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1, ensure_ascii=False)
    print(json.dumps(res, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
