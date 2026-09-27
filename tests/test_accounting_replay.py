from datetime import date, datetime

import pytest

from astraquant.data.market_coordinates import PriceUse
from astraquant.execution.market_data import (
    ExecutionAvailability,
    ExecutionPriceDecision,
    RawExecutionBar,
    TradabilityState,
)
from astraquant.portfolio.replay import AccountingReplayError, run_accounting_only_replay


def _decision(use: PriceUse, price: float, *, side: str) -> ExecutionPriceDecision:
    bar = RawExecutionBar(
        ticker="2330",
        session_date=date(2026, 1, 5),
        open=price,
        high=price + 5,
        low=price - 5,
        close=price,
    )
    trad = TradabilityState(
        ticker="2330",
        session_date=date(2026, 1, 5),
        observed_trade=True,
        valid_ohlc=True,
        buy_blocked=False,
        sell_blocked=False,
        reason="OBSERVED",
    )
    return ExecutionPriceDecision(
        availability=ExecutionAvailability.EXECUTABLE,
        use=use,
        side=side,
        field="close",
        price=price,
        reason="OK",
        bar=bar,
        tradability=trad,
    )


def test_accounting_only_replay_passes_core_gates():
    result = run_accounting_only_replay(
        ticker="2330",
        quantity=100,
        opening_cash=200000.0,
        signal_source="declared adjusted research signal",
        sizing_decision=_decision(PriceUse.SIZING, 1000.0, side="buy"),
        entry_decision=_decision(PriceUse.ENTRY, 1000.0, side="buy"),
        stop_observation_decision=_decision(PriceUse.STOP_OBSERVATION, 980.0, side="sell"),
        mark_decision=_decision(PriceUse.MARK, 1050.0, side="sell"),
        exit_decision=_decision(PriceUse.EXIT, 1100.0, side="sell"),
        entry_at=datetime(2026, 1, 5, 9, 0),
        entry_settlement_due=datetime(2026, 1, 7),
        exit_at=datetime(2026, 1, 12, 13, 30),
        exit_settlement_due=datetime(2026, 1, 14),
    )

    assert result.checks.passed
    assert result.pre_exit_valuation.nav == 205000.0
    assert result.final_cash == 210000.0
    assert result.realized_pnl == 10000.0


def test_accounting_only_replay_requires_declared_signal_source():
    result = run_accounting_only_replay(
        ticker="2330",
        quantity=100,
        opening_cash=200000.0,
        signal_source="",
        sizing_decision=_decision(PriceUse.SIZING, 1000.0, side="buy"),
        entry_decision=_decision(PriceUse.ENTRY, 1000.0, side="buy"),
        stop_observation_decision=_decision(PriceUse.STOP_OBSERVATION, 980.0, side="sell"),
        mark_decision=_decision(PriceUse.MARK, 1050.0, side="sell"),
        exit_decision=_decision(PriceUse.EXIT, 1100.0, side="sell"),
        entry_at=datetime(2026, 1, 5, 9, 0),
        entry_settlement_due=datetime(2026, 1, 7),
        exit_at=datetime(2026, 1, 12, 13, 30),
        exit_settlement_due=datetime(2026, 1, 14),
    )

    assert not result.checks.signal_source_declared
    assert not result.checks.passed


def test_accounting_only_replay_rejects_wrong_price_use():
    with pytest.raises(AccountingReplayError):
        run_accounting_only_replay(
            ticker="2330",
            quantity=100,
            opening_cash=200000.0,
            signal_source="declared",
            sizing_decision=_decision(PriceUse.SIZING, 1000.0, side="buy"),
            entry_decision=_decision(PriceUse.MARK, 1000.0, side="buy"),
            stop_observation_decision=_decision(PriceUse.STOP_OBSERVATION, 980.0, side="sell"),
            mark_decision=_decision(PriceUse.MARK, 1050.0, side="sell"),
            exit_decision=_decision(PriceUse.EXIT, 1100.0, side="sell"),
            entry_at=datetime(2026, 1, 5, 9, 0),
            entry_settlement_due=datetime(2026, 1, 7),
            exit_at=datetime(2026, 1, 12, 13, 30),
            exit_settlement_due=datetime(2026, 1, 14),
        )
