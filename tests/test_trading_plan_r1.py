from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from astraquant.research.trading_plan_r1 import (
    COMMISSION, SLIPPAGE, TAX, SCHEMAS, TradingPlanR1,
    concat_ledgers, load_r1_config, load_tables, metrics, run_backtest, run_daily,
)


def fixture(*, stocks=("1101",), closes=(104.0,), changes=None):
    sessions = pd.bdate_range("2020-01-01", periods=80 + len(closes)).strftime("%Y-%m-%d").tolist()
    rows = []
    for stock in stocks:
        for i, day in enumerate(sessions):
            close = 100.0 if i < 80 else closes[i - 80]
            opening = 100.0 if i < 80 else (103.0 if i == 80 else close)
            row = dict(date=day, stock=stock, open=opening, high=max(opening, close) + 1,
                       low=min(opening, close) - 1, close=close, volume=10000.0,
                       source_kind="synthetic", eligible=True, available_date=day,
                       source="synthetic_owner_pool", rs=80.0, suspended=False,
                       limit_up_price=120.0, limit_down_price=80.0, corporate_action=None,
                       stop_fill_price=float("nan"))
            if changes:
                row.update(changes.get((stock, i), {}))
            rows.append(row)
    return pd.DataFrame(rows), sessions


def execute(bars, sessions, *, mode="backtest", run_id="test", entry_mode="close"):
    runner = run_backtest if mode == "backtest" else run_daily
    return runner(bars, run_id=run_id, sessions=sessions, start=sessions[80], entry_mode=entry_mode)


def sold(engine):
    f = engine.ledger.table("fills")
    return f[f.side.eq("sell") & f.fill.fillna(False)]


class OwnerAcceptance(unittest.TestCase):
    def test_01_signal_close_over_pivot_cap(self):
        p, days = fixture(closes=(106.0,))
        engine = execute(p, days)
        d = engine.ledger.table("decisions").iloc[0]
        self.assertEqual(d.status, "REJECTED")
        self.assertEqual(d.reject_reason, "price_cap_exceeded")
        self.assertEqual(d.price_cap, 105.0)
        self.assertEqual(engine.cash, 1_000_000)
        self.assertFalse(engine.ledger.table("fills").fill.any())

    def test_02_signal_day_gap_over_five_percent(self):
        p, days = fixture(changes={("1101", 80): {"open": 106.0, "high": 107.0}})
        engine = execute(p, days)
        d = engine.ledger.table("decisions").iloc[0]
        self.assertEqual(d.status, "REJECTED")
        self.assertEqual(d.reject_reason, "gap_up_over_5pct")
        self.assertFalse(engine.ledger.table("fills").fill.any())

    def test_02b_signal_day_limit_up(self):
        p, days = fixture(changes={("1101", 80): {"limit_up_price": 104.0}})
        engine = execute(p, days)
        self.assertEqual(engine.ledger.table("decisions").iloc[0].reject_reason, "limit_up")
        self.assertEqual(engine.cash, 1_000_000)
        self.assertFalse(engine.ledger.table("fills").fill.any())

    def test_03_suspension_or_no_volume_is_not_a_close(self):
        for patch in ({"suspended": True}, {"volume": 0.0}):
            with self.subTest(patch=patch):
                patch = {**patch, "open": 99.0, "high": 101.0, "low": 90.0, "close": 99.0}
                p, days = fixture(closes=(104.0, 99.0), changes={("1101", 81): patch})
                engine = execute(p, days)
                self.assertEqual(len(sold(engine)), 0)
                self.assertIn("1101", engine.positions)
                m = metrics(engine.ledger.tables()).iloc[0]
                self.assertEqual(m.closed_count, 0)
                self.assertEqual(m.open_count, 1)
                self.assertTrue(pd.isna(m.net_win_rate))

    def test_04_stop_has_priority_over_same_day_close_exit_signal(self):
        p, days = fixture(closes=(104.0, 99.0), changes={
            ("1101", 81): {"open": 103.0, "high": 104.0, "low": 98.0, "close": 99.0}})
        engine = execute(p, days)
        f = sold(engine)
        self.assertEqual(len(f), 1)
        self.assertEqual(f.iloc[0].reason, "stop_price_assumption")
        self.assertEqual(f.iloc[0].fill_price, 100.0)
        self.assertEqual(f.iloc[0].fill_date, days[81])
        self.assertEqual(len(engine.positions), 0)
        self.assertFalse(engine.ledger.table("fills").reason.eq("sma20_next_open").any())

    def test_05_intraday_stop_observed_gap_fill_not_clipped(self):
        p, days = fixture(closes=(104.0, 90.0), changes={
            ("1101", 81): {"open": 103.0, "high": 104.0, "low": 80.0,
                           "close": 90.0, "stop_fill_price": 85.0}})
        engine = execute(p, days)
        f = sold(engine).iloc[0]
        self.assertEqual(f.fill_price, 85.0)
        self.assertEqual(f.reason, "stop_observed")
        self.assertLess(f.net_return, -0.07)
        buy = engine.ledger.table("fills").query("side == 'buy'").iloc[0]
        self.assertAlmostEqual(f.pnl, 85 * f.quantity * (1 - COMMISSION - TAX - SLIPPAGE)
                               - 104 * buy.quantity * (1 + COMMISSION + SLIPPAGE))
        self.assertAlmostEqual(engine.cash, 1_000_000 + f.pnl)

    def test_06_capacity_rs_desc_stock_asc_and_blocked_opportunities(self):
        stocks = ("1107", "1104", "1102", "1106", "1103", "1105", "1101")
        changes = {(s, 80): {"rs": 90.0 if s in {"1106", "1107"} else 80.0} for s in stocks}
        p, days = fixture(stocks=stocks, changes=changes)
        engine = execute(p, days)
        f = engine.ledger.table("fills")
        buys = f[f.side.eq("buy") & f.fill.fillna(False)]
        self.assertEqual(buys.stock.tolist(), ["1106", "1107", "1101", "1102", "1103"])
        e = engine.ledger.table("equity").iloc[0]
        self.assertEqual([x["stock"] for x in e.blocked_opportunities], ["1104", "1105"])
        self.assertTrue(all(x["reason"] == "max_positions" for x in e.blocked_opportunities))
        self.assertEqual(len(engine.positions), 5)
        self.assertTrue(all(pos.entry_cash <= 70_000 for pos in engine.positions.values()))

    def test_07_missing_held_bar_truncates_and_freezes_portfolio(self):
        p, days = fixture(closes=(104.0, 103.0, 102.0))
        p = p[~((p.stock == "1101") & (p.date == days[81]))]
        engine = execute(p, days)
        f = engine.ledger.table("fills")
        self.assertEqual(int(f.truncated.sum()), 1)
        self.assertEqual(f[f.truncated].iloc[0].status, "TRUNCATED")
        self.assertEqual(len(sold(engine)), 0)
        e = engine.ledger.table("equity")
        self.assertFalse(bool(e.iloc[0].frozen))
        self.assertTrue(e.iloc[1:].frozen.all())
        self.assertTrue(e.iloc[1:].equity.isna().all())
        m = metrics(engine.ledger.tables()).iloc[0]
        self.assertEqual(m.truncated_count, 1)
        self.assertEqual(m.closed_count, 0)
        self.assertEqual(m.open_count, 0)
        self.assertTrue(pd.isna(m.final_equity))

    def test_08_open_end_position_excluded_from_closed_win_rate(self):
        p, days = fixture()
        engine = execute(p, days)
        m = metrics(engine.ledger.tables()).iloc[0]
        self.assertEqual(m.open_count, 1)
        self.assertEqual(m.closed_count, 0)
        self.assertTrue(pd.isna(m.net_win_rate))
        self.assertEqual(len(sold(engine)), 0)
        self.assertAlmostEqual(m.final_equity, 1_000_000 - sum(r["cost"] for r in engine.ledger.rows["fills"]))

    def test_09_close_exit_signal_effective_next_open_only(self):
        # A higher consolidation pivot and lower base floor allow SMA exit above stop.
        changes = {("1101", i): {"open": 99.0, "high": 101.0, "low": 89.0,
                                 "close": 90.0 if i == 25 else 100.0} for i in range(20, 80)}
        changes[("1101", 81)] = {"open": 101.0, "high": 102.0, "low": 98.5, "close": 99.0}
        changes[("1101", 82)] = {"open": 98.0, "high": 110.0, "low": 80.0, "close": 108.0}
        p, days = fixture(closes=(104.0, 99.0, 108.0), changes=changes)
        # The 90 close may itself affect BB history; assert the intended entry exists.
        engine = execute(p, days)
        f = sold(engine)
        self.assertEqual(len(f), 1)
        self.assertEqual(f.iloc[0].reason, "sma20_next_open")
        self.assertEqual(f.iloc[0].date, days[81])
        self.assertEqual(f.iloc[0].fill_date, days[82])
        self.assertEqual(f.iloc[0].fill_price, 98.0)
        self.assertEqual(f.iloc[0].holding_sessions, 2)


class SharedSchemaAndContracts(unittest.TestCase):
    def test_daily_intent_save_reload_same_row_and_same_metrics(self):
        p, days = fixture(closes=(104.0, 90.0), changes={
            ("1101", 81): {"open": 103.0, "high": 104.0, "low": 80.0,
                           "close": 90.0, "stop_fill_price": 85.0}})
        daily = TradingPlanR1(run_id="daily", mode="daily", sessions=days)
        daily.prepare_session(p, days[80])
        before = daily.ledger.table("fills")
        self.assertEqual(before.iloc[0].status, "INTENT")
        self.assertTrue(pd.isna(before.iloc[0].fill_price))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "state.json"
            daily.save(path)
            daily = TradingPlanR1.load(path)
            daily.reconcile_session(days[80], observed_at=days[81])
            self.assertEqual(daily.ledger.table("fills").iloc[0].row_id, before.iloc[0].row_id)
            self.assertEqual(len(daily.ledger.table("fills")), len(before))
            daily.prepare_session(p, days[81])
            daily.reconcile_session(days[81], observed_at=pd.Timestamp(days[81]) + pd.offsets.BDay())
        back = execute(p, days, run_id="back")
        a, b = back.ledger.tables(), daily.ledger.tables()
        for name in SCHEMAS:
            self.assertEqual(tuple(a[name].columns), tuple(b[name].columns))
            self.assertEqual(a[name].dtypes.astype(str).tolist(), b[name].dtypes.astype(str).tolist())
        joined = concat_ledgers(a, b)
        m = metrics(joined)
        self.assertEqual(len(m), 2)
        for col in ("closed_count", "net_win_rate", "avg_loss", "expectancy", "final_equity"):
            self.assertAlmostEqual(float(m.iloc[0][col]), float(m.iloc[1][col]))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            concat_ledgers(a, a)

    def test_daily_runner_matches_backtest(self):
        p, days = fixture(closes=(104.0, 90.0))
        a = execute(p, days, run_id="a")
        b = execute(p, days, mode="daily", run_id="b")
        m = metrics(concat_ledgers(a.ledger.tables(), b.ledger.tables()))
        self.assertEqual(m.expectancy.iloc[0], m.expectancy.iloc[1])
        self.assertEqual(m.final_equity.iloc[0], m.final_equity.iloc[1])

    def test_consolidation_latest_above_day_excluded_and_minimum_ten(self):
        changes = {("1101", 70): {"open": 103.0, "high": 105.0, "low": 102.0, "close": 104.0}}
        p, days = fixture(closes=(105.0,), changes=changes)
        engine = execute(p, days)
        d = engine.ledger.table("decisions").iloc[0]
        self.assertEqual(d.base_sessions, 9)
        self.assertEqual(d.reject_reason, "base_too_short")

    def test_fallback_sixty_prior_sessions_not_signal_high_or_low(self):
        p, days = fixture(changes={("1101", 80): {"low": 60.0, "high": 200.0}})
        engine = execute(p, days)
        d = engine.ledger.table("decisions").iloc[0]
        self.assertEqual(d.base_sessions, 60)
        self.assertEqual(d.pivot, 100.0)
        self.assertEqual(d.structure_stop, 100.0)
        self.assertEqual(d.stop_price, 100.0)
        # A close entry cannot be stopped by an earlier low on the same day.
        self.assertEqual(len(sold(engine)), 0)

    def test_next_open_gap_stop_price_is_actual_open(self):
        p, days = fixture(closes=(104.0, 89.0), changes={
            ("1101", 81): {"open": 88.0, "high": 90.0, "low": 87.0, "close": 89.0}})
        engine = execute(p, days)
        self.assertEqual(sold(engine).iloc[0].fill_price, 88.0)
        self.assertLess(sold(engine).iloc[0].net_return, -0.07)

    def test_costs_exact_and_no_zero_fee_path(self):
        p, days = fixture(closes=(104.0, 90.0))
        engine = execute(p, days)
        f = engine.ledger.table("fills")
        for _, r in f[f.fill].iterrows():
            gross = r.fill_price * r.quantity
            self.assertAlmostEqual(r.commission, gross * 0.001425 * 0.6)
            self.assertAlmostEqual(r.tax, gross * 0.003 if r.side == "sell" else 0)
            self.assertAlmostEqual(r.slippage, gross * 0.002)
            self.assertAlmostEqual(r.cost, r.commission + r.tax + r.slippage)
        self.assertAlmostEqual(engine.cash, 1_000_000 + f.cash_flow.sum())

    def test_no_future_source_or_real_bars_allowed(self):
        p, days = fixture(changes={("1101", 80): {"available_date": "2030-01-01"}})
        engine = execute(p, days)
        self.assertEqual(engine.ledger.table("decisions").iloc[0].status, "REJECTED")
        p.source_kind = "source"
        with self.assertRaisesRegex(ValueError, "synthetic"):
            execute(p, days)

    def test_reconciliation_idempotent(self):
        p, days = fixture()
        engine = execute(p, days)
        original = engine.cash
        before = engine.ledger.table("fills")
        engine.reconcile_session(days[80], observed_at=days[80])
        self.assertEqual(engine.cash, original)
        pd.testing.assert_frame_equal(before, engine.ledger.table("fills"))

    def test_unexecutable_stop_stays_pending_until_next_tradable_open(self):
        p, days = fixture(closes=(104.0, 99.0, 103.0), changes={
            ("1101", 81): {"open": 103.0, "high": 104.0, "low": 98.0, "close": 99.0, "volume": 0.0},
            ("1101", 82): {"open": 102.0, "high": 104.0, "low": 101.0, "close": 103.0}})
        engine = execute(p, days)
        f = sold(engine)
        self.assertEqual(len(f), 1)
        self.assertEqual(f.iloc[0].reason, "stop_pending_next_open")
        self.assertEqual(f.iloc[0].fill_date, days[82])
        self.assertEqual(f.iloc[0].fill_price, 102.0)
        self.assertEqual(f.iloc[0].date, days[81])

    def test_daily_stop_intent_exists_before_reconciliation_same_row_filled(self):
        p, days = fixture(closes=(104.0, 90.0), changes={
            ("1101", 81): {"open": 103.0, "high": 104.0, "low": 80.0,
                           "close": 90.0, "stop_fill_price": 85.0}})
        engine = TradingPlanR1(run_id="daily", mode="daily", sessions=days)
        engine.prepare_session(p, days[80])
        engine.reconcile_session(days[80], observed_at=days[81])
        engine.prepare_session(p, days[81])
        f = engine.ledger.table("fills")
        intent = f[f.side.eq("sell")].iloc[0]
        self.assertEqual(intent.status, "INTENT")
        self.assertFalse(bool(intent.fill))
        engine.reconcile_session(days[81], observed_at=pd.Timestamp(days[81]) + pd.offsets.BDay())
        actual = sold(engine).iloc[0]
        self.assertEqual(actual.row_id, intent.row_id)
        self.assertEqual(actual.fill_price, 85.0)

    def test_four_csv_tables_reload_through_same_metrics(self):
        import json
        p, days = fixture(closes=(104.0, 90.0))
        engine = execute(p, days)
        tables = engine.ledger.tables()
        with tempfile.TemporaryDirectory() as folder:
            for name, frame in tables.items():
                frame = frame.copy()
                for col in frame:
                    if frame[col].dtype == object:
                        frame[col] = frame[col].map(lambda v: json.dumps(v) if isinstance(v, (dict, list)) else v)
                frame.to_csv(Path(folder) / f"synthetic_{name}.csv", index=False)
            restored = load_tables(folder)
        pd.testing.assert_frame_equal(metrics(tables), metrics(restored))


class EngineeringRevisions(unittest.TestCase):
    def test_10_entry_modes_different_prices_and_correct_rejection_sessions(self):
        p, days = fixture(closes=(104.0, 103.0), changes={
            ("1101", 81): {"open": 102.0, "high": 104.0, "low": 101.0, "close": 103.0}})
        close = execute(p, days, run_id="close")
        opening = execute(p, days, run_id="open", entry_mode="next_open")
        a = close.ledger.table("fills").query("side == 'buy' and fill == True").iloc[0]
        b = opening.ledger.table("fills").query("side == 'buy' and fill == True").iloc[0]
        self.assertEqual(a.fill_price, 104.0)
        self.assertEqual(a.fill_date, days[80])
        self.assertEqual(b.fill_price, 102.0)
        self.assertEqual(b.date, days[80])
        self.assertEqual(b.fill_date, days[81])
        self.assertEqual(opening.positions["1101"].stop_price, 100.0)
        scenarios = [
            ({("1101", 80): {"open": 106.0, "high": 107.0}}, "gap_up_over_5pct", None),
            ({("1101", 80): {"close": 106.0, "high": 107.0}}, "price_cap_exceeded", None),
            ({("1101", 80): {"limit_up_price": 104.0}}, "limit_up", None),
            ({("1101", 81): {"open": 110.0, "high": 111.0, "low": 108.0, "close": 109.0}}, None, "price_cap_exceeded"),
            ({("1101", 81): {"open": 104.0, "high": 105.0, "low": 102.0, "close": 103.0, "limit_up_price": 104.0}}, None, "limit_up"),
        ]
        for patch, close_reason, open_reason in scenarios:
            with self.subTest(patch=patch):
                changes = {("1101", 81): {"open": 102.0, "high": 104.0, "low": 101.0, "close": 103.0}}
                changes.update(patch)
                bars, sessions = fixture(closes=(104.0, 103.0), changes=changes)
                for mode, reason in (("close", close_reason), ("next_open", open_reason)):
                    engine = execute(bars, sessions, entry_mode=mode)
                    decision = engine.ledger.table("decisions").iloc[0]
                    if reason:
                        self.assertEqual(decision.status, "REJECTED")
                        self.assertEqual(decision.reject_reason, reason)
                    else:
                        self.assertEqual(decision.status, "FILLED")
        self.assertEqual(metrics(concat_ledgers(close.ledger.tables(), opening.ledger.tables())).entry_mode.tolist(), ["close", "next_open"])

    def test_11_all_reject_reasons_primary_unchanged(self):
        p, days = fixture(closes=(106.0,), changes={
            ("1101", 80): {"open": 106.0, "high": 107.0, "low": 105.0, "close": 106.0}})
        engine = execute(p, days)
        row = engine.ledger.table("decisions").iloc[0]
        self.assertEqual(row.reject_reason, "price_cap_exceeded")
        self.assertEqual(row.reject_reasons, ["price_cap_exceeded", "gap_up_over_5pct"])
        counts = metrics(engine.ledger.tables()).iloc[0].reject_reason_counts
        self.assertEqual(counts, {"price_cap_exceeded": 1, "gap_up_over_5pct": 1})

    def test_next_open_pending_state_save_restore_and_daily_parity(self):
        p, days = fixture(closes=(104.0, 103.0), changes={
            ("1101", 81): {"open": 102.0, "high": 104.0, "low": 101.0, "close": 103.0}})
        engine = TradingPlanR1(run_id="saved", mode="daily", sessions=days, entry_mode="next_open")
        engine.prepare_session(p, days[80])
        engine.reconcile_session(days[80], observed_at=days[81])
        self.assertEqual(engine.cash, 1_000_000)
        self.assertEqual(metrics(engine.ledger.tables()).iloc[0].pending_entry_count, 1)
        original = engine.ledger.table("fills").iloc[0].row_id
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "pending.json"
            engine.save(path)
            engine = TradingPlanR1.load(path)
        engine.prepare_session(p, days[81])
        engine.reconcile_session(days[81], observed_at=pd.Timestamp(days[81]) + pd.offsets.BDay())
        self.assertEqual(engine.ledger.table("fills").iloc[0].row_id, original)
        self.assertEqual(engine.ledger.table("fills").iloc[0].fill_price, 102.0)
        back = execute(p, days, run_id="back", entry_mode="next_open")
        self.assertEqual(engine.cash, back.cash)
        self.assertEqual(engine.positions["1101"].entry_price, back.positions["1101"].entry_price)

    def test_next_open_new_holding_can_stop_same_session(self):
        p, days = fixture(closes=(104.0, 99.0), changes={
            ("1101", 81): {"open": 102.0, "high": 103.0, "low": 98.0, "close": 99.0}})
        engine = execute(p, days, entry_mode="next_open")
        exit_row = sold(engine).iloc[0]
        self.assertEqual(exit_row.fill_price, 100.0)
        self.assertEqual(exit_row.fill_date, days[81])
        self.assertEqual(exit_row.holding_sessions, 0)

    def test_next_open_intraday_stop_does_not_release_opening_capacity(self):
        stocks = tuple(f"110{i}" for i in range(1, 7))
        changes = {("1106", 80): {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0}}
        changes.update({(s, 81): {"open": 103.0, "high": 104.0, "low": 102.0, "close": 103.0} for s in stocks})
        changes[("1106", 81)].update(close=104.0, high=105.0)
        changes.update({(s, 82): {"open": 103.0, "high": 104.0, "low": 102.0, "close": 103.0} for s in stocks})
        changes[("1101", 82)]["low"] = 99.0
        p, days = fixture(stocks=stocks, closes=(104.0, 103.0, 103.0), changes=changes)
        engine = execute(p, days, entry_mode="next_open")
        d = engine.ledger.table("decisions")
        last = d[d.stock.eq("1106")].iloc[0]
        self.assertEqual(last.reject_reason, "max_positions")
        self.assertEqual(len(engine.positions), 4)
        self.assertNotIn("1106", engine.positions)

    def test_next_open_last_signal_is_pending_no_future_fill(self):
        p, days = fixture()
        engine = execute(p, days, entry_mode="next_open")
        m = metrics(engine.ledger.tables()).iloc[0]
        self.assertEqual(m.pending_entry_count, 1)
        self.assertEqual(m.open_count, 0)
        self.assertEqual(engine.cash, 1_000_000)
        self.assertFalse(engine.ledger.table("fills").fill.any())

    def test_config_fixed_bollinger_and_invalid_entry_mode(self):
        root = Path(__file__).resolve().parents[1]
        config = load_r1_config(root / "configs/research/trading_plan_r1.yaml")
        self.assertEqual(config["bollinger"]["ddof"], 0)
        p, days = fixture()
        with self.assertRaisesRegex(ValueError, "entry_mode"):
            execute(p, days, entry_mode="invalid")

    def test_stop_anchor_is_raw_fill_price_not_fee_inclusive_basis(self):
        p, days = fixture(closes=(104.0, 103.0), changes={
            ("1101", 25): {"open": 99.0, "high": 101.0, "low": 89.0, "close": 90.0},
            ("1101", 81): {"open": 102.0, "high": 104.0, "low": 101.0, "close": 103.0}})
        for mode, raw_price in (("close", 104.0), ("next_open", 102.0)):
            with self.subTest(entry_mode=mode):
                engine = execute(p, days, entry_mode=mode)
                pos = engine.positions["1101"]
                self.assertAlmostEqual(pos.stop_price, raw_price * 0.93)
                self.assertGreater(pos.entry_cash / pos.quantity, raw_price)


if __name__ == "__main__":
    unittest.main()
