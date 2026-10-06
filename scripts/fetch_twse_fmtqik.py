#!/usr/bin/env python3
"""AQ-EXP-CAL-003 — 逐月取 TWSE FMTQIK，建立 E1 期間的權威交易日集合。

端點（公開，無需認證）：

    https://www.twse.com.tw/en/exchangeReport/FMTQIK?response=csv&date=YYYYMM01

一次回一個月的每日市場成交資訊，有資料的日期即為該月的開市日。
2016-01 至 2021-12 共 72 個月，循序取得、每次之間固定間隔。

取數紀律（以「請求單位」＝單一月份為粒度）：
  單次阻擋 → 該月立即標 UNKNOWN，執行端永不重試、不換同義查詢、不換端點，
             以相同或更慢的間隔繼續其他月份。
  連續兩次或累計三次阻擋 → 立即停止整條端點，保留已取得部分，回報當下狀態。
  被擋月份的補取一律須 Owner 裁定後另案發工，不在本腳本內處理。

輸出：
    out/twse_fmtqik_raw/FMTQIK_YYYYMM.csv   每月原始回應（原樣留存）
    out/aq_exp_cal_003_twse_sessions.csv    date,source_month
    out/aq_exp_cal_003_fetch_log.json       逐月狀態與停止原因

本腳本只取數，不做判定。判定在 AQ-EXP-CAL-003 的分析步驟。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "out" / "twse_fmtqik_raw"
SESSIONS = ROOT / "out" / "aq_exp_cal_003_twse_sessions.csv"
LOG = ROOT / "out" / "aq_exp_cal_003_fetch_log.json"

ENDPOINT = "https://www.twse.com.tw/en/exchangeReport/FMTQIK?response=csv&date={ym}01"
UA = "AstraQuant-AQ-EXP-CAL-003 (research; one request per month)"

# 疑似阻擋的特徵。命中即視為被擋，不重試、不改寫查詢。
BLOCK_MARKERS = (
    "security", "blocked", "forbidden", "too many requests",
    "rate limit", "<html", "<!doctype",
)
DATE_RE = re.compile(r'"(\d{4})/(\d{2})/(\d{2})"')


def months(start: str, end: str) -> list[str]:
    y0, m0 = int(start[:4]), int(start[4:])
    y1, m1 = int(end[:4]), int(end[4:])
    out, y, m = [], y0, m0
    while (y, m) <= (y1, m1):
        out.append(f"{y}{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def classify(status: int, body: bytes) -> tuple[str, str]:
    """回傳 (status_label, detail)。只分三種：OK / BLOCKED / EMPTY_OR_BAD。"""
    if status != 200:
        return ("BLOCKED" if status in (403, 429, 503) else "EMPTY_OR_BAD",
                f"http {status}")
    text = body.decode("ms950", errors="replace")
    low = text[:2000].lower()
    for marker in BLOCK_MARKERS:
        if marker in low:
            return "BLOCKED", f"response looks like a block page ({marker})"
    if "Highlights of Daily Trading" not in text:
        return "EMPTY_OR_BAD", "expected FMTQIK header not present"
    if not DATE_RE.search(text):
        return "EMPTY_OR_BAD", "no dated rows"
    return "OK", ""


def parse_dates(body: bytes, ym: str) -> list[str]:
    text = body.decode("ms950", errors="replace")
    out = []
    for y, m, d in DATE_RE.findall(text):
        if f"{y}{m}" == ym:                      # 只收該月，避開表頭或備註誤匹配
            out.append(f"{y}-{m}-{d}")
    return sorted(set(out))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="201601")
    ap.add_argument("--end", default="202112")
    ap.add_argument("--interval", type=float, default=4.0,
                    help="每次請求之間的間隔秒數")
    ap.add_argument("--timeout", type=float, default=30.0)
    args = ap.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    wanted = months(args.start, args.end)
    log: dict[str, object] = {
        "endpoint_template": ENDPOINT,
        "months_requested": len(wanted),
        "interval_seconds": args.interval,
        "stopped_early": False,
        "stop_reason": None,
        "months": {},
    }
    rows: list[tuple[str, str]] = []
    consecutive_blocks = 0
    total_blocks = 0

    for i, ym in enumerate(wanted):
        url = ENDPOINT.format(ym=ym)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=args.timeout) as resp:
                status, body = resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            status, body = exc.code, exc.read() or b""
        except Exception as exc:                  # noqa: BLE001 - 網路層任何失敗都標起來
            log["months"][ym] = {"status": "UNKNOWN", "detail": f"{type(exc).__name__}: {exc}"}
            print(f"{ym} UNKNOWN {exc}", file=sys.stderr)
            time.sleep(args.interval)
            continue

        label, detail = classify(status, body)
        if label == "OK":
            consecutive_blocks = 0
            (RAW_DIR / f"FMTQIK_{ym}.csv").write_bytes(body)
            dates = parse_dates(body, ym)
            rows.extend((d, ym) for d in dates)
            log["months"][ym] = {"status": "OK", "sessions": len(dates)}
            print(f"{ym} OK {len(dates)} sessions")
        else:
            log["months"][ym] = {"status": "UNKNOWN", "detail": f"{label}: {detail}"}
            print(f"{ym} UNKNOWN {label}: {detail}", file=sys.stderr)
            if label == "BLOCKED":
                consecutive_blocks += 1
                total_blocks += 1
                # 單次阻擋只標 UNKNOWN，絕不重試、不換同義查詢、不換端點。
                # 連續兩次或累計三次 → 停整條端點。
                if consecutive_blocks >= 2 or total_blocks >= 3:
                    log["stopped_early"] = True
                    log["stop_reason"] = (
                        f"blocked at {ym}; consecutive={consecutive_blocks}, "
                        f"cumulative={total_blocks}; stopped the whole endpoint "
                        "without retrying or rewriting any query")
                    print(f"STOP: blocked at {ym}", file=sys.stderr)
                    break
        if i + 1 < len(wanted):
            time.sleep(args.interval)

    ok = [m for m, v in log["months"].items() if v["status"] == "OK"]
    unknown = [m for m in wanted if log["months"].get(m, {}).get("status") != "OK"]
    log["months_ok"] = len(ok)
    log["months_unknown"] = len(unknown)
    log["months_unknown_list"] = unknown
    log["blocked_total"] = total_blocks
    log["block_policy"] = ("single block -> mark UNKNOWN, never retried; "
                           "2 consecutive or 3 cumulative -> stop the endpoint")
    log["total_sessions"] = len({d for d, _ in rows})

    rows.sort()
    SESSIONS.write_text(
        "date,source_month\n" + "".join(f"{d},{m}\n" for d, m in rows), encoding="utf-8")
    LOG.write_text(json.dumps(log, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nOK {len(ok)} / UNKNOWN {len(unknown)} months; "
          f"{log['total_sessions']} distinct sessions")
    # 被擋屬於「已回報的狀態」，不是腳本失敗，回傳 0 讓結果照常留存。
    return 0


if __name__ == "__main__":
    sys.exit(main())
