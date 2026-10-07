"""Synthetic checks for the S1 extension; no runtime/private data is opened."""
import ast
from pathlib import Path
import unittest

import numpy as np
import pandas as pd


def load_s1():
    # Compile the actual extension's pure functions without legacy layer1 imports.
    path = Path(__file__).resolve().parents[1] / "scripts/source_pit_feature_matrix_layer1.py"
    tree = ast.parse(path.read_text())
    nodes = [n for n in tree.body if
             (isinstance(n, ast.FunctionDef) and n.name.startswith("_s1_")) or
             (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id.startswith("S1_")
                                               for t in n.targets))]
    namespace = {"np": np, "pd": pd, "SOURCE_REVISION": "SYNTHETIC"}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    return namespace


S1 = load_s1()


def fixture():
    dates = pd.bdate_range("2015-01-02", periods=350)
    parts = []
    for stock, growth, start, volume in [
        ("1101", .001, 0, 2_000_000), ("1102", .002, 0, 100),
        ("1103", .003, 0, 3_000_000), ("1104", .0025, 200, 2_000_000),
        ("0050", .004, 0, 3_000_000)]:
        x = np.arange(len(dates)-start)
        parts.append(pd.DataFrame(dict(date=dates[start:], stock_id=stock,
            close=100 * (1+growth)**x, Trading_Volume=volume, Trading_money=100_000_000)))
    prices = pd.concat(parts, ignore_index=True)
    tape = prices[["date", "stock_id"]].copy()
    tape["market"] = np.where(tape["stock_id"].eq("1103"), "TPEx", "TWSE")
    tape["observed_trade"], tape["valid_ohlc"] = True, True
    return dates, prices, tape


def fundamentals():
    revenue, financials = [], []
    for stock in ["1101", "1102", "1103", "1104"]:
        months = pd.date_range("2013-01-01", periods=60, freq="MS")
        revenue.append(pd.DataFrame(dict(date=months, stock_id=stock,
            available_date=months + pd.Timedelta(days=14), revenue=100*1.03**np.arange(len(months)))))
        quarters = pd.period_range("2012Q1", periods=24, freq="Q").to_timestamp(how="end").normalize()
        financials.append(pd.DataFrame(dict(date=quarters, stock_id=stock,
            available_date=quarters + pd.Timedelta(days=46), type="EPS",
            value=1 + .04*np.arange(len(quarters))**2)))
    return pd.concat(revenue, ignore_index=True), pd.concat(financials, ignore_index=True)


class S1Tests(unittest.TestCase):
    def test_whole_market_rs_denominator_includes_illiquid_otc_excludes_etf(self):
        dates, prices, tape = fixture()
        out = S1["_s1_technical"](prices, tape).set_index(["date", "stock"])
        for stock, expected in [("1101", 100/3), ("1102", 200/3), ("1103", 100)]:
            row = out.loc[(dates[-1], stock)]
            self.assertEqual(row.rs_denominator, 3)
            self.assertAlmostEqual(row.rs, expected)
        self.assertFalse(out.loc[(dates[-1], "1102")].liq_ok)
        self.assertNotIn("0050", out.index.get_level_values("stock"))

    def test_short_flag_and_left_censored_history(self):
        dates, prices, tape = fixture()
        out = S1["_s1_technical"](prices, tape).set_index(["date", "stock"])
        self.assertFalse(out.loc[(dates[149], "1101")].rs_short)
        self.assertTrue(pd.isna(out.loc[(dates[149], "1101")].rs))
        new = out.loc[(dates[-1], "1104")]
        self.assertTrue(new.rs_short)
        self.assertEqual(new.rs_denominator, 3)
        self.assertAlmostEqual(new.rs, 200/3)

    def test_historical_market_transition_never_uses_emerging_history(self):
        dates, prices, tape = fixture()
        tape.loc[tape.stock_id.eq("1102") & tape.date.lt(dates[200]), "market"] = "EMERGING"
        out = S1["_s1_technical"](prices, tape).set_index(["date", "stock"])
        self.assertNotIn((dates[100], "1102"), out.index)
        row = out.loc[(dates[-1], "1102")]
        self.assertTrue(row.rs_short)
        self.assertEqual(row.rs_denominator, 2)

    def test_weekly_inputs_never_use_current_week_and_slope_is_week_over_week(self):
        dates, prices, tape = fixture()
        day = dates[-3]
        before = S1["_s1_technical"](prices, tape).set_index(["date", "stock"]).loc[(day, "1101")]
        changed = prices.copy()
        mask = changed.stock_id.eq("1101") & changed.date.dt.to_period("W-FRI").eq(day.to_period("W-FRI"))
        changed.loc[mask, "close"] *= 100
        after = S1["_s1_technical"](changed, tape).set_index(["date", "stock"]).loc[(day, "1101")]
        for field in ["wk_close", "wk_ma6", "wk_ma20", "wk_ma6_prev", "wk_ma20_prev", "wk_trend_ok"]:
            self.assertEqual(before[field], after[field])
        self.assertTrue(before.wk_trend_ok)
        self.assertLess(before.wk_available_date, day)

    def test_incomplete_history_does_not_skip_missing_market_session(self):
        dates, prices, tape = fixture()
        tape.loc[tape.stock_id.eq("1103") & tape.date.eq(dates[-25]), "valid_ohlc"] = False
        out = S1["_s1_technical"](prices, tape).set_index(["date", "stock"])
        row = out.loc[(dates[-1], "1103")]
        self.assertTrue(pd.isna(row.rs))
        self.assertFalse(row.rs_short)
        self.assertEqual(row.rs_denominator, 2)

    def test_revenue_asof_exact_available_date_and_exact_prior_month(self):
        revenue, _ = fundamentals()
        events = S1["_s1_growth_events"](revenue, "rev")
        date = pd.Timestamp("2015-03-15")
        keys = pd.DataFrame(dict(date=[date-pd.Timedelta(days=1), date], stock=["1101", "1101"]))
        result = S1["_s1_asof"](keys, events, "rev")
        self.assertEqual(result.iloc[0].rev_period_date, pd.Timestamp("2015-02-01"))
        self.assertEqual(result.iloc[1].rev_period_date, pd.Timestamp("2015-03-01"))
        missing = revenue[~(revenue.stock_id.eq("1101") & revenue.date.eq(pd.Timestamp("2014-03-01")))]
        event = S1["_s1_growth_events"](missing, "rev")
        row = event[event.stock_id.eq("1101") & event.rev_period_date.eq(pd.Timestamp("2015-03-01"))].iloc[0]
        self.assertTrue(pd.isna(row.rev_yoy))

    def test_eps_acceleration_requires_three_consecutive_yoy_quarters(self):
        _, financials = fundamentals()
        financials = financials[~(financials.stock_id.eq("1101") & financials.date.eq(pd.Timestamp("2014-12-31")))]
        event = S1["_s1_growth_events"](financials, "eps")
        row = event[event.stock_id.eq("1101") & event.eps_period_date.eq(pd.Timestamp("2015-06-30"))].iloc[0]
        self.assertTrue(pd.isna(row.eps_yoy_prev2))
        self.assertFalse(row.eps_yoy > row.eps_yoy_prev1 > row.eps_yoy_prev2)

    def test_ten_independent_source_checks_and_all_flags_and(self):
        _, prices, tape = fixture()
        revenue, financials = fundamentals()
        panel = S1["_s1_panel"](prices, tape, revenue, financials)
        checks, summary, sample = S1["_s1_audit"](panel, prices, tape, revenue, financials)
        self.assertEqual(len(summary), 10)
        self.assertTrue(summary.result.eq("PASS").all(), checks[~checks["match"]].to_string())
        self.assertTrue(panel.eligibility.equals(panel[S1["S1_FLAGS"]].all(axis=1)))
        self.assertEqual(panel.index.names, ["date", "stock"])
        self.assertTrue(panel.excl_ok.all())


if __name__ == "__main__":
    unittest.main()
