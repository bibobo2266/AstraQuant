import pandas as pd

from astraquant.data.dividend_reconciliation import (
    AnnouncementPrecision,
    PrimaryClass,
    ReconciliationInputs,
    aggregate_reconciliation,
    announcement_precision,
    finmind_components,
    official_rows,
    reconcile_dividend_components,
)


INPUTS = ReconciliationInputs(
    source_revision="fb8b042b46dc38838d103544ca17da10286c7bfe",
    dividend_blob_sha="dividend-sha",
    official_blob_sha="official-sha",
    acquired_at="2026-10-04T01:31:41Z",
)


def _dividend(**overrides):
    row = {
        "stock_id": "1234",
        "date": "2020-06-01",
        "available_date": "2020-05-01",
        "AnnouncementDate": "2020-05-01",
        "AnnouncementTime": "15:30:45",
        "CashExDividendTradingDate": "2020-06-15",
        "StockExDividendTradingDate": "2020-06-15",
        "CashDividendPaymentDate": "2020-07-01",
        "CashEarningsDistribution": 2.0,
        "CashStatutorySurplus": 0.5,
        "CashDividend": 999.0,
        "StockEarningsDistribution": 1.0,
        "StockStatutorySurplus": 0.5,
        "StockDividend": 999.0,
    }
    row.update(overrides)
    return pd.DataFrame([row])


def _official(**overrides):
    row = {
        "stock_id": "1234",
        "event_date": "2020-06-15",
        "known_date": "",
        "event_type": "ex_right_dividend",
        "cash_per_share": 2.5,
        "share_multiplier": 1.15,
        "rights_ratio": 150.0,
        "subscription_price": "",
        "market": "TPEx",
        "source_url": "https://www.tpex.org.tw/example",
        "source_name": "TPEx exDailyQ",
        "confidence": "official",
        "notes": "",
    }
    row.update(overrides)
    return pd.DataFrame([row])


def _class(dividend, official):
    events, _, _ = reconcile_dividend_components(
        dividend,
        official,
        inputs=INPUTS,
    )
    assert len(events) == 1
    return events.iloc[0]


def test_announcement_precision_does_not_promote_date_only_to_midnight():
    exact, ts = announcement_precision(
        pd.Series({"AnnouncementDate": "2020-05-01", "AnnouncementTime": "15:30:45"})
    )
    assert exact is AnnouncementPrecision.EXACT_TIMESTAMP
    assert ts.isoformat() == "2020-05-01T15:30:45"

    date_only, ts2 = announcement_precision(
        pd.Series({"AnnouncementDate": "2020-05-01", "AnnouncementTime": ""})
    )
    assert date_only is AnnouncementPrecision.DATE_ONLY
    assert ts2.isoformat() == "2020-05-01T00:00:00"


def test_finmind_stock_conversion_is_explicitly_source_specific():
    components = finmind_components(
        _dividend(),
        source_revision=INPUTS.source_revision,
        dividend_blob_sha=INPUTS.dividend_blob_sha,
    )
    cash = components[components["component_kind"].eq("CASH_DIVIDEND")].iloc[0]
    stock = components[components["component_kind"].eq("STOCK_DIVIDEND")].iloc[0]

    assert cash["cash_per_share"] == 2.5
    assert cash["source_unit_semantics"] == "NTD_PER_PRE_EVENT_SHARE"
    assert stock["source_distribution_value"] == 1.5
    assert stock["share_multiplier"] == 1.15
    assert stock["source_unit_semantics"] == "NTD_PER_PRE_EVENT_SHARE"


def test_tpex_stock_conversion_candidate_is_preserved_but_not_certified():
    row = official_rows(
        _official(),
        source_revision=INPUTS.source_revision,
        official_blob_sha=INPUTS.official_blob_sha,
    ).iloc[0]
    assert row["rights_ratio"] == 150.0
    assert row["expected_multiplier_from_raw_unit"] == 1.15
    assert row["stock_unit_semantics"] == "FROZEN_PARSER_DIVIDE_BY_1000_UNIT_UNVERIFIED"
    assert not bool(row["stock_unit_verified"])


def test_cash_only_component_and_value_can_be_consistent():
    dividend = _dividend(
        StockExDividendTradingDate=None,
        StockEarningsDistribution=0.0,
        StockStatutorySurplus=0.0,
        StockDividend=0.0,
    )
    official = _official(share_multiplier=1.0, rights_ratio=0.0)
    row = _class(dividend, official)
    assert row["primary_class"] == PrimaryClass.COMPONENT_VALUE_CONSISTENT.value
    assert not row["flag_component_missing"]
    assert not row["flag_value_conflict"]
    assert not row["flag_unit_conflict"]
    assert not row["flag_stock_unit_unverified"]


def test_same_date_component_missing_is_not_hidden_by_stock_date_match():
    row = _class(
        _dividend(
            StockExDividendTradingDate=None,
            StockEarningsDistribution=0.0,
            StockStatutorySurplus=0.0,
            StockDividend=0.0,
        ),
        _official(),
    )
    assert row["primary_class"] == PrimaryClass.SAME_DATE_COMPONENT_MISSING.value
    assert row["flag_component_missing"]


def test_same_date_value_conflict_is_separate_from_component_presence():
    row = _class(_dividend(CashEarningsDistribution=1.0), _official())
    assert row["normalized_cash_present"]
    assert row["primary_class"] == PrimaryClass.VALUE_OR_UNIT_CONFLICT.value
    assert row["flag_value_conflict"]


def test_tpex_stock_value_stays_insufficient_until_unit_semantics_are_verified():
    row = _class(_dividend(), _official(share_multiplier=1.20, rights_ratio=150.0))
    assert row["primary_class"] == PrimaryClass.INSUFFICIENT_EVIDENCE.value
    assert row["flag_stock_unit_unverified"]
    assert not row["flag_unit_conflict"]


def test_twse_date_match_remains_insufficient_without_frozen_economics():
    twse = _official(
        market="TWSE",
        source_name="TWSE TWT49U",
        cash_per_share="",
        share_multiplier="",
        rights_ratio="",
    )
    row = _class(_dividend(), twse)
    assert row["official_row_ids"]
    assert row["normalized_component_ids"]
    assert row["primary_class"] == PrimaryClass.INSUFFICIENT_EVIDENCE.value
    assert row["flag_official_economics_insufficient"]


def test_bidirectional_official_only_and_normalized_only_are_not_conflated():
    official_only, _, _ = reconcile_dividend_components(
        pd.DataFrame(columns=_dividend().columns),
        _official(),
        inputs=INPUTS,
    )
    assert official_only.iloc[0]["primary_class"] == PrimaryClass.GENUINE_SOURCE_EVENT_MISSING.value
    assert official_only.iloc[0]["flag_official_without_normalized"]

    normalized_only, _, _ = reconcile_dividend_components(
        _dividend(),
        pd.DataFrame(columns=_official().columns),
        inputs=INPUTS,
    )
    assert normalized_only.iloc[0]["primary_class"] == PrimaryClass.INSUFFICIENT_EVIDENCE.value
    assert normalized_only.iloc[0]["flag_normalized_without_official"]


def test_primary_classes_conserve_event_count_in_each_scope():
    d = pd.concat(
        [
            _dividend(stock_id="1234"),
            _dividend(
                stock_id="5678",
                date="2020-07-01",
                CashExDividendTradingDate="2020-07-15",
                StockExDividendTradingDate=None,
                StockEarningsDistribution=0.0,
                StockStatutorySurplus=0.0,
                StockDividend=0.0,
            ),
        ],
        ignore_index=True,
    )
    o = pd.concat(
        [
            _official(stock_id="1234"),
            _official(
                stock_id="5678",
                event_date="2020-07-15",
                cash_per_share=2.5,
                share_multiplier=1.0,
                rights_ratio=0.0,
            ),
        ],
        ignore_index=True,
    )
    events, _, _ = reconcile_dividend_components(
        d,
        o,
        inputs=INPUTS,
        research_tickers={"1234"},
    )
    agg = aggregate_reconciliation(events)
    for _, g in agg.groupby("scope"):
        assert int(g["count"].sum()) == int(g["scope_total"].iloc[0])


def test_frozen_sources_record_revision_history_as_not_retained():
    events, raw, _ = reconcile_dividend_components(
        _dividend(),
        _official(),
        inputs=INPUTS,
    )
    assert not bool(raw.iloc[0]["revision_history_retained"])
    assert bool(events.iloc[0]["flag_historical_revision_cancel_unknown"])
