import pandas as pd

from astraquant.data.corporate_actions import (
    NormalizedCorporateActionKind,
    build_finmind_normalized_actions,
    normalized_actions_frame,
)


def test_finmind_cash_uses_cash_ex_date_and_statutory_surplus():
    d = pd.DataFrame([{
        "stock_id": "1101",
        "date": "2014-07-23",
        "CashExDividendTradingDate": "2014-07-17",
        "StockExDividendTradingDate": None,
        "available_date": "2014-06-20 10:00:00",
        "AnnouncementDate": "2014-06-19 09:00:00",
        "CashDividendPaymentDate": "2014-08-08",
        "CashEarningsDistribution": 1.5,
        "CashStatutorySurplus": 0.2,
        "CashDividend": 99.0,
        "StockEarningsDistribution": 0.0,
        "StockStatutorySurplus": 0.0,
        "StockDividend": 0.0,
    }])

    actions = build_finmind_normalized_actions(d)

    assert len(actions) == 1
    a = actions[0]
    assert a.kind is NormalizedCorporateActionKind.CASH_DIVIDEND
    assert a.effective_date.isoformat() == "2014-07-17"
    assert a.cash_per_share == 1.7
    assert a.known_at.isoformat() == "2014-06-20T10:00:00"
    assert a.payment_at.isoformat() == "2014-08-08T00:00:00"
    assert a.unit_semantics == "cash_per_pre_event_share"


def test_finmind_stock_uses_stock_ex_date_and_currency_per_share_formula():
    d = pd.DataFrame([{
        "stock_id": "2330",
        "CashExDividendTradingDate": None,
        "StockExDividendTradingDate": "2026-07-15",
        "available_date": "2026-05-01 12:00:00",
        "AnnouncementDate": "2026-04-30 12:00:00",
        "CashDividendPaymentDate": None,
        "CashEarningsDistribution": 0.0,
        "CashStatutorySurplus": 0.0,
        "CashDividend": 0.0,
        "StockEarningsDistribution": 0.8,
        "StockStatutorySurplus": 0.2,
        "StockDividend": 88.0,
    }])

    actions = build_finmind_normalized_actions(d)

    assert len(actions) == 1
    a = actions[0]
    assert a.kind is NormalizedCorporateActionKind.STOCK_DIVIDEND
    assert a.effective_date.isoformat() == "2026-07-15"
    assert a.share_multiplier == 1.1
    assert a.unit_semantics == "stock_dividend_currency_per_share_divided_by_10"


def test_cash_and_stock_components_keep_separate_ex_dates():
    d = pd.DataFrame([{
        "stock_id": "1234",
        "CashExDividendTradingDate": "2026-07-01",
        "StockExDividendTradingDate": "2026-07-03",
        "available_date": "2026-06-01",
        "AnnouncementDate": "2026-05-31",
        "CashDividendPaymentDate": "2026-07-20",
        "CashEarningsDistribution": 2.0,
        "CashStatutorySurplus": 0.0,
        "CashDividend": 2.0,
        "StockEarningsDistribution": 1.0,
        "StockStatutorySurplus": 0.0,
        "StockDividend": 1.0,
    }])

    frame = normalized_actions_frame(build_finmind_normalized_actions(d))

    assert frame["effective_date"].dt.strftime("%Y-%m-%d").tolist() == [
        "2026-07-01",
        "2026-07-03",
    ]
    assert frame["event_kind"].tolist() == [
        "CASH_DIVIDEND",
        "STOCK_DIVIDEND",
    ]
