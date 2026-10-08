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
                 and n.name in {"_s3_limit_tick", "_s3_limit_bounds", "_s3_limit_no_close_reference", "_s3_limit_quote_number"}]
        cls.rules = {}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), cls.rules)

    def limits(self, *args, **kwargs):
        return tuple(str(v) for v in self.rules["_s3_limit_bounds"](*args, **kwargs))

    def test_ordinary_prices_round_inwards_across_tick_bands(self):
        self.assertEqual(self.limits("40.60"), ("44.65", "36.55"))
        self.assertEqual(self.limits("95"), ("104.5", "85.5"))

    def test_ex_dividend_bounds_given_unrounded_reference(self):
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

    def test_no_close_uses_bid_above_base_or_ask_below_base(self):
        reference = self.rules["_s3_limit_no_close_reference"]
        self.assertEqual(str(reference("1.95", "1.92", "1.98")), "1.95")
        self.assertEqual(str(reference("1.95", "1.96", "1.98")), "1.96")
        self.assertEqual(str(reference("1.95", "1.90", "1.92")), "1.92")

    def test_no_close_retains_verified_base_with_no_or_one_quote(self):
        reference = self.rules["_s3_limit_no_close_reference"]
        self.assertEqual(str(reference("1.95")), "1.95")
        self.assertEqual(str(reference("1.95", last_bid="1.92")), "1.95")
        self.assertEqual(str(reference("1.95", last_ask="1.98")), "1.95")
        self.assertEqual(str(reference("1.95", last_ask="1.92")), "1.92")

    def test_no_close_rejects_invalid_base_and_crossed_quotes(self):
        reference = self.rules["_s3_limit_no_close_reference"]
        for args in [(None,), ("NaN",), ("0",), ("1", "1.2", "1.1"), ("1", "0")]:
            with self.assertRaises((ValueError, ArithmeticError)):
                reference(*args)

    def test_zero_bid_ask_sentinel_is_absence_but_zero_close_is_invalid(self):
        number = self.rules["_s3_limit_quote_number"]
        self.assertIsNone(number("0.00", bid_ask=True))
        self.assertIsNone(number("----"))
        self.assertEqual(str(number("1,200.00", bid_ask=True)), "1200.00")
        for value in ["0.00", "-1", "NaN"]:
            with self.assertRaises((ValueError, ArithmeticError)):
                number(value)

class SupplementFlowTests(unittest.TestCase):
    """Run the real supplement entry point with synthetic, offline I/O only."""

    def run_flow(self, case, *, wrong_reference=False):
        import contextlib
        import gzip
        import hashlib
        import io
        import json
        import os
        import tempfile
        from unittest.mock import patch

        source_path = Path(__file__).resolve().parents[1] / "scripts/source_pit_feature_matrix_layer1.py"
        source = source_path.read_text()
        if wrong_reference:
            original = 'specials[key] = (str(row[4]).strip(), str(row[dividend_col]).strip())'
            self.assertEqual(source.count(original), 1)
            source = source.replace(original,
                'specials[key] = (str(row[9 if market == "twse" else 11]).strip(), str(row[dividend_col]).strip())')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "scripts").mkdir()
            (root / "scripts/source_pit_feature_matrix_layer1.py").write_text(source)
            inputs, evidence = root / "inputs", root / "results/trading_plan_r1/limit_source_probe"
            inputs.mkdir()
            evidence.mkdir(parents=True)
            output = root / "out/limit_supplement"
            (output / "finmind_responses").mkdir(parents=True)
            (output / "official_quote_inputs").mkdir()
            days = pd.bdate_range("2019-01-02", periods=18)
            date, previous, earlier = days[-1], days[-2], days[-3]
            stock = "1101"
            rows = [dict(date=day, stock_id=sid, close=100.0, max=np.nan, min=np.nan,
                         market="TPEx") for sid in [stock, "9999"] for day in days]
            raw = pd.DataFrame(rows)
            events = []
            official_rows = []

            def official_row(day, sid, reference, auction, dividend):
                return [f"{day.year-1911}/{day.month:02}/{day.day:02}", sid, "synthetic",
                        "100", reference, "", "", "", "", auction, dividend, auction, dividend]

            def quote(day, bid, ask, *, absent_stock=False):
                payload = dict(stat="ok", date=day.strftime("%Y%m%d"), tables=[dict(
                    fields=["代號", "收盤", "最後買價", "最後賣價"],
                    data=[["8888" if absent_stock else stock, "----", bid, ask]])])
                (output / f"official_quote_inputs/tpex_{day.date()}.json").write_text(json.dumps(payload))

            if case == "ex_dividend":
                raw.loc[raw.stock_id.eq(stock), "market"] = "TWSE"
            if case in {"ex_dividend", "event_seed"}:
                event_day = date if case == "ex_dividend" else previous
                official_rows.append(official_row(event_day, stock, "610.50", "611", "610.50"))
            if case == "chain":
                raw.loc[raw.stock_id.eq(stock) & raw.date.isin([earlier, previous]), "close"] = np.nan
                quote(earlier, "101", "102")
                quote(previous, "100", "100.50")
            if case in {"event_seed", "missing_quote", "unverified_seed"}:
                raw.loc[raw.stock_id.eq(stock) & raw.date.eq(previous), "close"] = np.nan
                quote(previous, "610", "612", absent_stock=case == "missing_quote")
            if case == "missing_session":
                raw = raw[~(raw.stock_id.eq(stock) & raw.date.eq(previous))]
            if case == "transfer":
                raw.loc[raw.stock_id.eq(stock) & raw.date.eq(previous), "market"] = "TWSE"
            if case == "ipo":
                raw = raw[~raw.stock_id.eq(stock) | raw.date.ge(days[-3])]
            if case in {"unverified_seed", "unverified_event", "verified_event"}:
                event_day = previous if case == "unverified_seed" else date
                events.append(dict(stock_id=stock, event_date=str(event_day.date()),
                    event_type="capital_reduction", notes="ref=50.89" if case == "verified_event" else "unverified"))
            pd.DataFrame(events, columns=["stock_id", "event_date", "event_type", "notes"]).to_csv(
                inputs / "corporate_actions_official.csv", index=False)
            # A fixed ten-row synthetic probe exercises the audit gate too.
            # These fixtures are not additional official stock-day comparisons.
            probe_day = date if case == "ex_dividend" else previous if case == "event_seed" else days[0]
            if not official_rows:
                official_rows.append(official_row(probe_day, "4000", "100", "100", "100"))
            for number in range(1, 10):
                official_rows.append(official_row(days[0], f"400{number}", "100", "100", "100"))
            fixture_market = "tpex" if case == "event_seed" else "twse"
            for market in ["twse", "tpex"]:
                for year in range(2019, 2022):
                    data = official_rows if market == fixture_market and year == 2019 else []
                    payload = dict(data=data) if market == "twse" else dict(tables=[dict(data=data)])
                    (evidence / f"official-{market}-{year}.json").write_text(json.dumps(payload))
            official_file = evidence / f"official-{fixture_market}-2019.json"
            official_hash = hashlib.sha256(official_file.read_bytes()).hexdigest()
            plan = []
            for row in official_rows:
                y, m, d = map(int, row[0].split("/"))
                special = row[4] == "610.50"
                plan.append(dict(date=f"{y+1911:04}-{m:02}-{d:02}", stock_id=row[1], market=fixture_market.upper(),
                    official_file=official_file.name, official_sha256=official_hash,
                    official_limit_up="671" if special else "110",
                    official_limit_down="550" if special else "90"))
            (evidence / "sample_plan.json").write_text(json.dumps(plan))
            source_manifest = dict(source_revision="3e7c4b6d9cde3b18942710fa977db02f89bffa0d", files=[
                dict(path="corporate_actions_official.csv", sha256=hashlib.sha256(
                    (inputs / "corporate_actions_official.csv").read_bytes()).hexdigest())])
            (inputs / "input_manifest.json").write_text(json.dumps(source_manifest))
            panel_path = root / "accepted_panel.parquet"
            panel = pd.DataFrame(dict(date=[date, date], stock=[stock, "9999"])).set_index(["date", "stock"])
            body = json.dumps(dict(status=200, data=[dict(date=str(date.date()), stock_id="9999",
                reference_price=100, limit_up=110, limit_down=90)])).encode()
            (output / f"finmind_responses/{date.date()}.json.gz").write_bytes(gzip.compress(body, mtime=0))
            nodes = [node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef)
                     and (node.name.startswith("_s3_limit_") or node.name == "_sha256")]
            namespace = dict(ROOT=root, OUT_ROOT=root / "out", Path=Path, os=os,
                             pd=pd, json=json, hashlib=hashlib)
            exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source_path), "exec"), namespace)
            real_sha = namespace["_sha256"]
            # Only the accepted panel's byte read is substituted; all other
            # file hashes, source selection and calculations run unchanged.
            namespace["_sha256"] = lambda path: (
                "2fc9680a3cbb74b15d690edbeb02ed03457b26c74dd682a877b1c6e93f8dc38e"
                if Path(path) == panel_path else real_sha(path))
            written = {}
            def read_parquet(path, **kwargs):
                if Path(path) == panel_path:
                    return panel.copy()
                year = int(Path(path).stem.rsplit("_", 1)[1])
                return raw[raw.date.dt.year.eq(year)].copy()
            def write_parquet(frame, path, **kwargs):
                written[Path(path).name] = frame.copy()
                Path(path).write_bytes(b"synthetic parquet output")
            with patch.dict(os.environ, dict(LIMIT_INPUT_ROOT=str(inputs), S1_PANEL_PATH=str(panel_path)), clear=True), \
                 patch.object(pd, "read_parquet", side_effect=read_parquet), \
                 patch.object(pd.DataFrame, "to_parquet", new=write_parquet), \
                 patch("urllib.request.urlopen", side_effect=AssertionError("offline fixture attempted network")), \
                 contextlib.redirect_stdout(io.StringIO()):
                try:
                    namespace["_s3_limit_supplement"]()
                except SystemExit as error:
                    self.assertEqual(str(error), "BLOCKED: unresolved limit inputs; evidence retained; no S3")
            return (written["price_limit_supplement_2019_2021.parquet"],
                    pd.read_csv(output / "unresolved.csv", dtype={"stock_id": str}),
                    pd.read_csv(output / "no_close_reference_trace.csv", dtype={"stock_id": str}),
                    json.loads((output / "manifest.json").read_text()))

    def assert_reference_selection(self, *, wrong_reference=False):
        result, unresolved, _, manifest = self.run_flow("ex_dividend", wrong_reference=wrong_reference)
        self.assertTrue(unresolved.empty)
        target = result[result.stock_id.eq("1101")].iloc[0]
        self.assertEqual(target.reference_input, "610.50")
        self.assertEqual((target.limit_up, target.limit_down), (671, 550))
        self.assertTrue(target.derived)
        self.assertEqual(target.source, "official_ex_right_reference")
        self.assertEqual(manifest["status"], "READY_FOR_REVIEW")

    def test_actual_source_selection_uses_reference_610_50_not_auction_611(self):
        self.assert_reference_selection()

    def test_wrong_auction_column_mutation_is_detected_by_actual_flow_assertions(self):
        with self.assertRaises(AssertionError) as detected:
            self.assert_reference_selection(wrong_reference=True)
        self.assertIn("'611' != '610.50'", str(detected.exception))

    def test_actual_flow_recurses_across_consecutive_no_close_sessions(self):
        result, unresolved, trace, _ = self.run_flow("chain")
        self.assertTrue(unresolved.empty)
        target = result[result.stock_id.eq("1101")].iloc[0]
        self.assertEqual(target.reference_input, "100.50")
        self.assertEqual((target.limit_up, target.limit_down), (110.5, 90.5))
        self.assertEqual(target.source, "official_no_close_bid_ask_rule")
        self.assertEqual(trace.previous_auction_base.tolist(), [100.0, 101.0])
        self.assertEqual(trace.next_reference.tolist(), [101.0, 100.5])

    def test_actual_flow_seeds_special_no_close_day_from_official_auction_base(self):
        result, unresolved, trace, _ = self.run_flow("event_seed")
        self.assertTrue(unresolved.empty)
        target = result[result.stock_id.eq("1101")].iloc[0]
        self.assertEqual(target.reference_input, "611")
        self.assertEqual((target.limit_up, target.limit_down), (672, 550))
        self.assertEqual(trace.previous_auction_base.tolist(), [611])

    def assert_rejected(self, case, reason):
        result, unresolved, _, manifest = self.run_flow(case)
        self.assertEqual(result.stock_id.tolist(), ["9999"])
        self.assertEqual(unresolved.stock_id.tolist(), ["1101"])
        self.assertEqual(unresolved.reason.tolist(), [reason])
        self.assertEqual(manifest["unresolved"], 1)
        self.assertEqual(manifest["status"], "BLOCKED_UNRESOLVED_INPUTS")
        self.assertFalse(manifest["s3_run"])

    def test_actual_flow_rejects_missing_previous_market_session(self):
        self.assert_rejected("missing_session", "previous_session_quote_missing")

    def test_actual_flow_rejects_missing_official_stock_quote(self):
        self.assert_rejected("missing_quote", "official_closing_quote_missing")

    def test_actual_flow_rejects_unverified_market_transfer(self):
        self.assert_rejected("transfer", "market_transfer_reference_unverified")

    def test_actual_flow_rejects_unverified_ipo_status(self):
        self.assert_rejected("ipo", "ipo_no_limit_status_unverified")

    def test_actual_flow_rejects_unverified_special_no_close_seed(self):
        self.assert_rejected("unverified_seed", "special_no_close_auction_base_unverified")

    def test_actual_flow_rejects_event_with_unverified_reference(self):
        self.assert_rejected("unverified_event", "special_event_reference_unresolved")

    def test_actual_flow_uses_verified_resumption_reference(self):
        result, unresolved, _, _ = self.run_flow("verified_event")
        self.assertTrue(unresolved.empty)
        target = result[result.stock_id.eq("1101")].iloc[0]
        self.assertEqual(target.reference_input, "50.89")
        self.assertEqual((target.limit_up, target.limit_down), (55.9, 45.85))
        self.assertEqual(target.source, "official_resumption_reference")


if __name__ == "__main__":
    unittest.main()
