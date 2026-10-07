"""Run the owner's ten synthetic acceptance cases and export four shared tables."""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from astraquant.research.trading_plan_r1 import concat_ledgers, metrics  # noqa: E402


CASES = {
    "test_01_signal_close_over_pivot_cap": "1 訊號日收盤超過樞紐×1.05",
    "test_02_signal_day_gap_over_five_percent": "2 訊號日跳空開高>5%",
    "test_02b_signal_day_limit_up": "2b 訊號日漲停",
    "test_03_suspension_or_no_volume_is_not_a_close": "3 停牌／無量不得正常平倉",
    "test_04_stop_has_priority_over_same_day_close_exit_signal": "4 同日停損優先",
    "test_05_intraday_stop_observed_gap_fill_not_clipped": "5 停損跳價記實際成交",
    "test_06_capacity_rs_desc_stock_asc_and_blocked_opportunities": "6 RS排序與超額阻擋",
    "test_07_missing_held_bar_truncates_and_freezes_portfolio": "7 資料中斷截尾並凍結權益",
    "test_08_open_end_position_excluded_from_closed_win_rate": "8 未平倉不併入closed勝率",
    "test_09_close_exit_signal_effective_next_open_only": "9 收盤出場次日開盤生效",
}


class CaseResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.passed = set()

    def addSuccess(self, test):
        super().addSuccess(test)
        self.passed.add(test._testMethodName)


def export_table(frame: pd.DataFrame, path: Path) -> None:
    frame = frame.copy()
    for col in frame:
        if frame[col].dtype == object:
            frame[col] = frame[col].map(
                lambda x: json.dumps(x, ensure_ascii=False, sort_keys=True)
                if isinstance(x, (dict, list)) else x
            )
    frame.to_csv(path, index=False, encoding="utf-8-sig")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "results" / "trading_plan_r1")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location("r1_synthetic_tests", ROOT / "tests" / "test_trading_plan_r1.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    suite = unittest.defaultTestLoader.loadTestsFromModule(module)
    result = unittest.TextTestRunner(verbosity=1, resultclass=CaseResult).run(suite)
    rows = [{"case": label, "test": name, "result": "PASS" if name in result.passed else "FAIL",
             "source_kind": "synthetic"} for name, label in CASES.items()]
    export_table(pd.DataFrame(rows), args.out / "synthetic_acceptance.csv")
    for row in rows:
        print(f"{row['case']} {row['result']}")
    if not result.wasSuccessful() or result.skipped or any(row["result"] != "PASS" for row in rows):
        return 1
    bars, sessions = module.fixture(closes=(104.0, 90.0), changes={
        ("1101", 81): {"open": 103.0, "high": 104.0, "low": 80.0,
                       "close": 90.0, "stop_fill_price": 85.0}})
    backtest = module.execute(bars, sessions, run_id="synthetic-backtest")
    daily = module.execute(bars, sessions, mode="daily", run_id="synthetic-daily")
    joined = concat_ledgers(backtest.ledger.tables(), daily.ledger.tables())
    for name, frame in joined.items():
        export_table(frame, args.out / f"synthetic_{name}.csv")
    export_table(metrics(joined), args.out / "synthetic_metrics.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
