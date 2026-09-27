from datetime import date

import pytest

from astraquant.data.market_coordinates import PriceUse
from astraquant.execution.market_data import (
    ExecutionAvailability,
    ExecutionPriceDecision,
    RawExecutionBar,
    TradabilityState,
)
from astraquant.portfolio.cash import CashAccount
from astraquant.portfolio.models import Position
from astraquant.portfolio.valuation import ValuationError, value_portfolio


def _mark(ticker: str, price: float, *, availability=ExecutionAvailability.EXECUTABLE):
    bar = RawExecutionBar(
        ticker=ticker,
        session_date=date(2026, 9, 24),
        open=price,
        high=price,
        low=price,
        close=price,
    )
    trad = TradabilityState(
        ticker=ticker,
        session_date=date(2026, 9, 24),
        observed_trade=True,
        valid_ohlc=True,
        buy_blocked=False,
        sell_blocked=False,
        reason="OBSERVED",
    )
    return ExecutionPriceDecision(
        availability=availability,
        use=PriceUse.MARK,
        side="sell",
        field="close",
        price=price if availability is ExecutionAvailability.EXECUTABLE else None,
        reason="OK" if availability is ExecutionAvailability.EXECUTABLE else "RAW_MISSING",
        bar=bar,
        tradability=trad,
    )


def test_nav_uses_raw_marks_cash_receivables_and_payables():
    cash = CashAccount(
        settled_cash=100000.0,
        pending_receivables=500.0,
        pending_payables=1000.0,
    )
    positions = {
        "2330": Position(ticker="2330", quantity=100, avg_cost=900.0),
        "2317": Position(ticker="2317", quantity=200, avg_cost=100.0),
    }

    valuation = value_portfolio(
        cash=cash,
        positions=positions,
        raw_mark_decisions={
            "2330": _mark("2330", 1000.0),
            "2317": _mark("2317", 120.0),
        },
    )

    assert valuation.market_value == 124000.0
    assert valuation.nav == 223500.0
    assert valuation.settled_cash == 100000.0
    assert valuation.pending_receivables == 500.0
    assert valuation.pending_payables == 1000.0


def test_missing_raw_mark_hard_fails():
    cash = CashAccount(settled_cash=100000.0)
    positions = {"2330": Position(ticker="2330", quantity=100, avg_cost=900.0)}

    with pytest.raises(ValuationError, match="missing RAW mark"):
        value_portfolio(cash=cash, positions=positions, raw_mark_decisions={})


def test_non_executable_mark_hard_fails():
    cash = CashAccount(settled_cash=100000.0)
    positions = {"2330": Position(ticker="2330", quantity=100, avg_cost=900.0)}

    with pytest.raises(ValuationError, match="not available"):
        value_portfolio(
            cash=cash,
            positions=positions,
            raw_mark_decisions={
                "2330": _mark(
                    "2330",
                    1000.0,
                    availability=ExecutionAvailability.NOT_EXECUTABLE,
                )
            },
        )


def test_non_mark_decision_hard_fails():
    cash = CashAccount(settled_cash=100000.0)
    positions = {"2330": Position(ticker="2330", quantity=100, avg_cost=900.0)}
    decision = _mark("2330", 1000.0)
    wrong_use = ExecutionPriceDecision(
        availability=decision.availability,
        use=PriceUse.EXIT,
        side=decision.side,
        field=decision.field,
        price=decision.price,
        reason=decision.reason,
        bar=decision.bar,
        tradability=decision.tradability,
    )

    with pytest.raises(ValuationError, match="use=EXIT"):
        value_portfolio(
            cash=cash,
            positions=positions,
            raw_mark_decisions={"2330": wrong_use},
        )
