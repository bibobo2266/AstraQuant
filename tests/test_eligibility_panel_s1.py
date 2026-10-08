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
    def test_owner_rs_boundary_250_closes_fail_251_closes_qualify(self):
        dates, prices, tape = fixture()
        out = S1["_s1_technical"](prices, tape).set_index(["date", "stock"])
        active, *_ = S1["_s1_prepare"](prices, tape)
        for day, count in [(dates[249], 0), (dates[250], 3)]:
            row = out.loc[(day, "1101")]
            reference = S1["_s1_reference_technical"](active, tape, day, "1101")
            self.assertEqual(row.rs_denominator, count)
            self.assertEqual(reference["rs_denominator"], count)
            self.assertFalse(row.rs_short)
            if count:
                self.assertAlmostEqual(row.return250, 1.001**250 - 1)
                self.assertAlmostEqual(row.rs, 100/3)
                self.assertAlmostEqual(reference["rs"], row.rs)
            else:
                self.assertTrue(pd.isna(row.return250))
                self.assertTrue(pd.isna(row.rs))

    def test_whole_market_empty_week_is_not_skipped_in_weekly_ma(self):
        dates, prices, tape = fixture()
        day = dates[-1]
        holiday = day.to_period("W-FRI") - 12
        prices = prices[prices.date.dt.to_period("W-FRI").ne(holiday)]
        tape = tape[tape.date.dt.to_period("W-FRI").ne(holiday)]
        out = S1["_s1_technical"](prices, tape).set_index(["date", "stock"])
        active, *_ = S1["_s1_prepare"](prices, tape)
        row = out.loc[(day, "1101")]
        reference = S1["_s1_reference_technical"](active, tape, day, "1101")
        for field in ["wk_ma20", "wk_ma20_prev"]:
            self.assertTrue(pd.isna(row[field]))
            self.assertTrue(pd.isna(reference[field]))
        for field in ["wk_close", "wk_ma6", "wk_ma6_prev"]:
            self.assertTrue(pd.notna(row[field]))
            self.assertAlmostEqual(row[field], reference[field])
        self.assertFalse(row.wk_trend_ok)
        self.assertFalse(reference["wk_trend_ok"])

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


class LimitRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / "scripts/source_pit_feature_matrix_layer1.py"
        tree = ast.parse(path.read_text())
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                 and n.name in {"_s3_limit_tick", "_s3_limit_bounds"}]
        cls.rules = {}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), cls.rules)

    def limits(self, *args, **kwargs):
        return tuple(str(v) for v in self.rules["_s3_limit_bounds"](*args, **kwargs))

    def test_ordinary_prices_round_inwards_across_tick_bands(self):
        self.assertEqual(self.limits("40.60"), ("44.65", "36.55"))
        self.assertEqual(self.limits("95"), ("104.5", "85.5"))

    def test_ex_dividend_uses_unrounded_reference_not_auction_base(self):
        self.assertEqual(self.limits("610.50"), ("671", "550"))

    def test_discount_rights_have_separate_upper_lower_bases(self):
        self.assertEqual(self.limits("67.19", "69"), ("75.9", "60.5"))

    def test_premium_rights_reverse_the_two_bases(self):
        self.assertEqual(self.limits("32", "30"), ("35.20", "27.0"))

    def test_no_limit_requires_explicit_status_and_minimum_cent_is_preserved(self):
        self.assertEqual(self.limits(None, no_limit=True), ("0", "0"))
        self.assertEqual(self.limits(".05"), ("0.06", "0.04"))
        self.assertEqual(self.limits(".01"), ("0.02", "0.01"))

    def test_invalid_reference_is_not_filled(self):
        for value in [None, "NaN", "0", "-1"]:
            with self.assertRaises((ValueError, ArithmeticError)):
                self.limits(value)


if __name__ == "__main__":
    unittest.main()
