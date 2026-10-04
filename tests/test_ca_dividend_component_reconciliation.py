from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


SCRIPT = Path(__file__).parents[1] / "scripts" / "ca_dividend_component_reconciliation.py"
SPEC = importlib.util.spec_from_file_location("ca_recon", SCRIPT)
assert SPEC and SPEC.loader
ca = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ca
SPEC.loader.exec_module(ca)


def _dividend(**overrides):
    row = {
        "stock_id": "2330",
        "CashExDividendTradingDate": "2019-06-24",
        "StockExDividendTradingDate": "",
        "CashEarningsDistribution": 8.0,
        "CashStatutorySurplus": 0.0,
        "StockEarningsDistribution": 0.0,
        "StockStatutorySurplus": 0.0,
        "AnnouncementDate": "2019-06-06",
        "AnnouncementTime": "15:47:30",
    }
    row.update(overrides)
    return pd.DataFrame([row])


def _official(**overrides):
    row = {
        "stock_id": "2330",
        "event_date": "2019-06-24",
        "event_type": "ex_right_dividend",
        "cash_per_share": "8.0",
        "share_multiplier": "",
        "rights_ratio": "",
        "market": "TPEx",
        "source_url": "https://example.test",
        "source_name": "TPEx exDailyQ",
        "confidence": "official",
        "known_date": "",
        "notes": "",
    }
    row.update(overrides)
    return pd.DataFrame([row])


def _build(dividend=None, official=None):
    start = pd.Timestamp("2015-01-01")
    end = pd.Timestamp("2021-12-31")
    comps = ca.build_normalized_components(
        _dividend() if dividend is None else dividend,
        source_revision="fixed",
        start=start,
        end=end,
    )
    offs = ca.build_official_rows(
        _official() if official is None else official,
        source_revision="fixed",
        start=start,
        end=end,
    )
    events, mappings = ca.reconcile_events(comps, offs)
    return comps, offs, events, mappings


def test_exact_announcement_time_is_not_collapsed_to_midnight():
    comps, _, _, _ = _build()
    assert comps.loc[0, "time_precision"] == "EXACT_TIME"
    assert comps.loc[0, "known_at_value"] == pd.Timestamp("2019-06-06 15:47:30")


def test_date_only_is_explicit_precision_not_exact_time():
    d = _dividend(AnnouncementTime="")
    comps, _, _, _ = _build(dividend=d)
    assert comps.loc[0, "time_precision"] == "DATE_ONLY"
    assert comps.loc[0, "known_at_value"] == pd.Timestamp("2019-06-06")


def test_matched_cash_component_and_value_can_be_consistent():
    _, _, events, _ = _build()
    assert len(events) == 1
    assert events.loc[0, "primary_class"] == "CONSISTENT_COMPONENTS_AND_VALUES"
    assert not bool(events.loc[0, "value_conflict_flag"])


def test_same_date_official_cash_without_normalized_cash_is_component_missing():
    d = _dividend(
        CashExDividendTradingDate="",
        CashEarningsDistribution=0.0,
        StockExDividendTradingDate="2019-06-24",
        StockEarningsDistribution=1.0,
    )
    _, _, events, _ = _build(dividend=d)
    assert events.loc[0, "primary_class"] == "DATE_MATCH_COMPONENT_MISSING"
    assert bool(events.loc[0, "cash_component_missing_flag"])


def test_same_date_cash_value_conflict_is_not_silently_accepted():
    o = _official(cash_per_share="7.5")
    _, _, events, _ = _build(official=o)
    assert events.loc[0, "primary_class"] == "VALUE_MULTIPLIER_OR_UNIT_CONFLICT"
    assert bool(events.loc[0, "value_conflict_flag"])


def test_tpex_stock_multiplier_uses_verified_shares_per_1000_semantics():
    d = _dividend(
        CashExDividendTradingDate="",
        CashEarningsDistribution=0.0,
        StockExDividendTradingDate="2019-06-24",
        StockEarningsDistribution=1.0,
    )
    o = _official(cash_per_share="", rights_ratio="100", share_multiplier="1.1")
    _, _, events, _ = _build(dividend=d, official=o)
    assert events.loc[0, "primary_class"] == "CONSISTENT_COMPONENTS_AND_VALUES"
    assert not bool(events.loc[0, "unit_unverified_flag"])


def test_twse_same_date_presence_is_insufficient_economic_evidence():
    o = _official(
        market="TWSE",
        source_name="TWSE TWT49U",
        cash_per_share="",
        rights_ratio="",
        share_multiplier="",
    )
    _, _, events, _ = _build(official=o)
    assert events.loc[0, "primary_class"] == "INSUFFICIENT_EVIDENCE"
    assert bool(events.loc[0, "evidence_insufficient_flag"])


def test_bidirectional_normalized_only_stays_insufficient_but_detailed_tpex_official_only_is_true_missing():
    start = pd.Timestamp("2015-01-01")
    end = pd.Timestamp("2021-12-31")
    comps = ca.build_normalized_components(
        _dividend(),
        source_revision="fixed",
        start=start,
        end=end,
    )
    offs = ca.build_official_rows(
        _official(stock_id="2317", event_date="2019-07-01"),
        source_revision="fixed",
        start=start,
        end=end,
    )
    events, _ = ca.reconcile_events(comps, offs)
    assert len(events) == 2
    classes = set(events["primary_class"])
    assert classes == {"INSUFFICIENT_EVIDENCE", "TRUE_SOURCE_EVENT_MISSING"}
    assert int(events["normalized_only"].sum()) == 1
    assert int(events["official_only"].sum()) == 1


def test_duplicate_official_same_event_gets_duplicate_revision_class():
    o = pd.concat(
        [_official(), _official(notes="second-source-row")],
        ignore_index=True,
    )
    _, _, events, _ = _build(official=o)
    assert events.loc[0, "primary_class"] == "DUPLICATE_REVISION_OR_CANCEL"
    assert bool(events.loc[0, "duplicate_or_multirow_flag"])


def test_event_primary_class_conservation_is_exact():
    d = pd.concat(
        [
            _dividend(),
            _dividend(stock_id="2317", CashExDividendTradingDate="2019-07-01"),
        ],
        ignore_index=True,
    )
    o = _official()
    comps, offs, events, _ = _build(dividend=d, official=o)
    agg = ca.aggregate(events, comps, offs, e1_start=pd.Timestamp("2016-01-04"))
    block = agg["source_all"]["warmup_plus_e1"]
    assert block["events"] == sum(block["classes"].values())


def test_finmind_stock_conversion_is_labeled_source_specific():
    d = _dividend(
        CashExDividendTradingDate="",
        CashEarningsDistribution=0.0,
        StockExDividendTradingDate="2019-06-24",
        StockEarningsDistribution=0.8,
        StockStatutorySurplus=0.2,
    )
    comps, _, _, _ = _build(dividend=d)
    assert comps.loc[0, "economic_value"] == 0.1
    assert comps.loc[0, "share_multiplier"] == 1.1
    assert comps.loc[0, "unit_evidence_status"] == "SOURCE_SPECIFIC_FINMIND_PAR10_CONVERSION"
