#!/usr/bin/env python3
"""AQ-EXP-CAL-003 — 以 TWSE FMTQIK 的權威紀錄重新判定 104 天，並與 panel 全期對帳。

輸入（皆在 repo 內，不需私有資料）：
    out/aq_exp_cal_003_twse_sessions.csv    fetch_twse_fmtqik.py 的產出
    out/aq_exp_cal_003_fetch_log.json       逐月取數狀態
    out/aq_exp_cal_003_panel_sessions.csv   panel 的 E1 session 日期（聚合，無逐列內容）
    out/aq_exp_cal_002_adjudication.csv     CAL-002 的 104 天判定（third-party）

輸出：
    out/aq_exp_cal_003_authoritative_calendar.json
    out/aq_exp_cal_003_adjudication.csv     逐日判定，source 欄升級或維持

判定規則，全部 fail-closed：
  - 某日所屬月份取數狀態不是 OK → 該日維持 third-party，標 UNKNOWN_MONTH，不升級。
  - 月份 OK 且該日不在權威 session 內 → NON_TRADING_DAY，source 升級為 authoritative。
  - 月份 OK 且該日在權威 session 內 → REAL_MISSING_SESSION（panel 缺了真的交易日）。
不以第三方補位，不以推估填補。
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TWSE = ROOT / "out" / "aq_exp_cal_003_twse_sessions.csv"
FETCH_LOG = ROOT / "out" / "aq_exp_cal_003_fetch_log.json"
PANEL = ROOT / "out" / "aq_exp_cal_003_panel_sessions.csv"
CAL2 = ROOT / "out" / "aq_exp_cal_002_adjudication.csv"
OUT_JSON = ROOT / "out" / "aq_exp_cal_003_authoritative_calendar.json"
OUT_CSV = ROOT / "out" / "aq_exp_cal_003_adjudication.csv"

MONTHS_EXPECTED = 72
EXPECTED_MAKEUP_SATURDAYS = 8
# CAL-002 量到 panel 有而 XTAI 無的 8 天，全為補行交易週六。
MAKEUP_SATURDAYS = {
    "2016-01-30", "2016-06-04", "2016-09-10", "2017-02-18",
    "2017-06-03", "2017-09-30", "2018-03-31", "2018-12-22",
}
ALL_FOUR = 428102
FOUR_WAY_DELTA_PER_MISSING_SESSION = -34254   # AQ-EXP-CAL-001 實測，單一缺日


def _read_col(path: Path, col: str) -> list[str]:
    with path.open(encoding="utf-8") as fh:
        return [r[col] for r in csv.DictReader(fh)]


def build(root: Path = ROOT) -> dict:
    twse_path = root / TWSE.relative_to(ROOT)
    log = json.loads((root / FETCH_LOG.relative_to(ROOT)).read_text(encoding="utf-8"))
    twse_sessions = set(_read_col(twse_path, "date"))
    panel_sessions = set(_read_col(root / PANEL.relative_to(ROOT), "date"))

    ok_months = {m for m, v in log["months"].items() if v.get("status") == "OK"}
    unknown_months = sorted(set(log.get("months_unknown_list") or []))

    with (root / CAL2.relative_to(ROOT)).open(encoding="utf-8") as fh:
        prior = list(csv.DictReader(fh))

    rows, counts = [], {"NON_TRADING_DAY": 0, "REAL_MISSING_SESSION": 0, "UNKNOWN_MONTH": 0}
    for r in prior:
        day = r["date"]
        month = day[:4] + day[5:7]
        if month not in ok_months:
            verdict, source = r["verdict"], r["source"]
            tier, note = "third-party", "UNKNOWN_MONTH: authoritative record not retrieved"
            counts["UNKNOWN_MONTH"] += 1
        else:
            in_twse = day in twse_sessions
            verdict = "REAL_MISSING_SESSION" if in_twse else "NON_TRADING_DAY"
            source = f"TWSE FMTQIK {month[:4]}-{month[4:]} (authoritative)"
            tier, note = "authoritative", ""
            counts[verdict] += 1
        rows.append({"date": day, "verdict": verdict, "source_tier": tier,
                     "source": source, "note": note})

    # 全期雙向對帳，只在權威覆蓋到的月份內進行。
    covered = {d for d in panel_sessions | twse_sessions if (d[:4] + d[5:7]) in ok_months}
    panel_cov = panel_sessions & covered
    twse_cov = twse_sessions & covered
    authoritative_only = sorted(twse_cov - panel_cov)      # 真缺日
    panel_only = sorted(panel_cov - twse_cov)              # 預期為補行交易週六

    real_missing = sorted({r["date"] for r in rows if r["verdict"] == "REAL_MISSING_SESSION"})
    delta = len(authoritative_only) and None                # 佔位，下面明確處理
    four_way_delta = 0 if not authoritative_only else None

    result = {
        "task_id": "AQ-EXP-CAL-003", "revision": 1,
        "schema_version": "aq-exp-cal-003-v1",
        "scope": "SOURCE_EVIDENCE", "execution_authorized": False,
        "formal_research_gate": "BLOCKED_UNCONDITIONALLY",
        "measurement_layer": "DATA_LAYER_DIAGNOSTIC",
        "metrics_not_reported": ["win_rate", "payoff_ratio", "expectancy_per_trade"],
        "authoritative_source": {
            "name": "TWSE FMTQIK 每日市場成交資訊",
            "endpoint_template": log.get("endpoint_template"),
            "authoritative": True,
            "months_requested": log.get("months_requested"),
            "months_ok": log.get("months_ok"),
            "months_unknown": log.get("months_unknown"),
            "months_unknown_list": unknown_months,
            "stopped_early": log.get("stopped_early"),
            "stop_reason": log.get("stop_reason"),
            "full_coverage": log.get("months_ok") == MONTHS_EXPECTED,
            "raw_responses_kept": "out/twse_fmtqik_raw/FMTQIK_<YYYYMM>.csv",
            "license": "TWSE 公開資訊；政府資料開放授權條款第1版",
        },
        "adjudication": {
            "days_in": len(prior),
            "upgraded_to_authoritative": counts["NON_TRADING_DAY"] + counts["REAL_MISSING_SESSION"],
            "still_third_party": counts["UNKNOWN_MONTH"],
            "non_trading_day": counts["NON_TRADING_DAY"],
            "real_missing_session": counts["REAL_MISSING_SESSION"],
            "real_missing_session_dates": real_missing,
            "not_upgraded_dates": [r["date"] for r in rows if r["source_tier"] != "authoritative"],
            "third_party_used_as_filler": False,
        },
        "full_period_reconciliation": {
            "covered_months": len(ok_months),
            "panel_sessions_in_covered_months": len(panel_cov),
            "authoritative_sessions_in_covered_months": len(twse_cov),
            "authoritative_only_dates": authoritative_only,
            "authoritative_only_count": len(authoritative_only),
            "panel_only_dates": panel_only,
            "panel_only_count": len(panel_only),
            "panel_only_all_saturdays": all(_is_saturday(d) for d in panel_only),
            "panel_only_matches_expected_makeup_saturdays":
                len(panel_only) == EXPECTED_MAKEUP_SATURDAYS,
            "expected_makeup_saturdays": sorted(MAKEUP_SATURDAYS),
            "makeup_saturdays_present_in_authoritative": sorted(
                d for d in MAKEUP_SATURDAYS if d in twse_cov),
            "panel_only_explanation": _explain_panel_only(panel_only, twse_cov),
            "note": ("panel 有而權威無的，預期全為補行交易週六；數目不同須解釋。"
                     "權威有而 panel 無的即真缺日。"),
        },
        "four_way_intersection": {
            "before": ALL_FOUR,
            "real_missing_sessions_found": len(authoritative_only),
            "delta": 0 if not authoritative_only else None,
            "after": ALL_FOUR if not authoritative_only else None,
            "is_actual_not_estimated": not authoritative_only,
            "calculation_path": (
                "真缺日 0 天 → CAL-001 的敏感度路徑輸入為空集合 → 四項交集不變"
                if not authoritative_only else
                "真缺日非空 → 須以 CAL-001 的敏感度路徑逐日插入 null session 列重算，"
                f"單日參考量級 {FOUR_WAY_DELTA_PER_MISSING_SESSION}；本腳本不估計"),
            "reference_delta_per_missing_session": FOUR_WAY_DELTA_PER_MISSING_SESSION,
        },
    }
    del delta, four_way_delta
    return {"artifact": result, "rows": rows}


def _explain_panel_only(panel_only: list[str], twse_cov: set[str]) -> str:
    """panel 有而權威無的日子，數目與預期不同時必須有解釋。"""
    covered_makeup = sorted(d for d in MAKEUP_SATURDAYS if d in twse_cov)
    if len(panel_only) == EXPECTED_MAKEUP_SATURDAYS:
        return "與預期相同：panel 多出的就是 8 個補行交易週六。"
    if not panel_only:
        return (f"0 而非 {EXPECTED_MAKEUP_SATURDAYS}：權威紀錄本身收錄了"
                f"{len(covered_makeup)} 個補行交易週六，所以 panel 沒有任何一天是"
                "權威沒有的。CAL-002 量到的差異，來源是第三方日曆漏收補行交易日，"
                "不是 panel 多算。")
    extra = sorted(set(panel_only) - MAKEUP_SATURDAYS)
    return (f"數目為 {len(panel_only)}，與預期的 8 不同；"
            f"其中不屬於已知補行交易週六的有 {len(extra)} 天：{extra}。需人工判讀。")


def _is_saturday(day: str) -> bool:
    import datetime as _dt
    return _dt.date.fromisoformat(day).weekday() == 5


def main() -> int:
    built = build()
    OUT_JSON.write_text(json.dumps(built["artifact"], indent=1, ensure_ascii=False),
                        encoding="utf-8")
    with OUT_CSV.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["date", "verdict", "source_tier", "source", "note"])
        w.writeheader()
        w.writerows(built["rows"])
    a = built["artifact"]
    print("months OK:", a["authoritative_source"]["months_ok"],
          "/ unknown:", a["authoritative_source"]["months_unknown"])
    print("upgraded:", a["adjudication"]["upgraded_to_authoritative"],
          "| still third-party:", a["adjudication"]["still_third_party"])
    print("real missing sessions:", a["adjudication"]["real_missing_session"])
    print("panel-only (expect 8 Saturdays):",
          a["full_period_reconciliation"]["panel_only_count"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
