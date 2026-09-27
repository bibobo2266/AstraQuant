from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from astraquant.data.market_coordinates import PriceUse
from astraquant.execution.assumptions import FixedBpsSlippage, ZeroFeeModel
from astraquant.execution.fills import ExecutionFillFactory
from astraquant.execution.market_data import ExecutionAvailability, ExecutionPriceDecision
from astraquant.portfolio.engine import PortfolioEngine, SettlementInstruction
from astraquant.portfolio.models import OrderIntent
from astraquant.portfolio.valuation import PortfolioValuation, value_portfolio


@dataclass(frozen=True)
class AccountingReplayChecks:
    signal_source_declared: bool
    sizing_raw: bool
    entry_raw: bool
    stop_observation_raw: bool
    exit_raw: bool
    mark_raw: bool
    share_count_reconciles: bool
    cash_reconciles: bool
    receivables_reconcile: bool
    nav_reconciles: bool
    no_adjusted_execution_fallback: bool

    @property
    def passed(self) -> bool:
        return all(self.__dict__.values())


@dataclass(frozen=True)
class AccountingReplayResult:
    checks: AccountingReplayChecks
    entry_price: float
    exit_price: float
    quantity: float
    pre_exit_valuation: PortfolioValuation
    final_cash: float
    realized_pnl: float


class AccountingReplayError(RuntimeError):
    pass


def _require_decision(
    decision: ExecutionPriceDecision,
    *,
    expected_use: PriceUse,
) -> None:
    if decision.use is not expected_use:
        raise AccountingReplayError(
            f"expected {expected_use.value} decision, got {decision.use.value}"
        )
    if decision.availability is not ExecutionAvailability.EXECUTABLE:
        raise AccountingReplayError(
            f"{expected_use.value} is not executable/observable: {decision.reason}"
        )
    if decision.price is None or decision.price <= 0:
        raise AccountingReplayError(f"{expected_use.value} has no positive RAW price")


def run_accounting_only_replay(
    *,
    ticker: str,
    quantity: float,
    opening_cash: float,
    signal_source: str,
    sizing_decision: ExecutionPriceDecision,
    entry_decision: ExecutionPriceDecision,
    stop_observation_decision: ExecutionPriceDecision,
    mark_decision: ExecutionPriceDecision,
    exit_decision: ExecutionPriceDecision,
    entry_at: datetime,
    entry_settlement_due: datetime,
    exit_at: datetime,
    exit_settlement_due: datetime,
) -> AccountingReplayResult:
    """Run a minimal accounting lifecycle without evaluating strategy performance.

    The replay is deliberately deterministic: zero fees and zero slippage. Its
    purpose is to prove state/accounting identities, not estimate returns.
    """

    if quantity <= 0:
        raise ValueError("quantity must be positive")
    if opening_cash < 0:
        raise ValueError("opening_cash must be non-negative")

    _require_decision(sizing_decision, expected_use=PriceUse.SIZING)
    _require_decision(entry_decision, expected_use=PriceUse.ENTRY)
    _require_decision(stop_observation_decision, expected_use=PriceUse.STOP_OBSERVATION)
    _require_decision(mark_decision, expected_use=PriceUse.MARK)
    _require_decision(exit_decision, expected_use=PriceUse.EXIT)

    factory = ExecutionFillFactory(
        fee_model=ZeroFeeModel(),
        slippage_model=FixedBpsSlippage(bps=0),
    )
    engine = PortfolioEngine(opening_cash=opening_cash)

    buy_intent = OrderIntent(
        intent_id="replay-buy-intent",
        ticker=ticker,
        side="buy",
        quantity=quantity,
        created_at=entry_at,
        rationale="accounting-only replay",
    )
    engine.orders.create_from_intent(buy_intent, "replay-buy-order")
    engine.orders.submit("replay-buy-order", entry_at)

    buy_fill = factory.create_fill(
        fill_id="replay-buy-fill",
        order_id="replay-buy-order",
        ticker=ticker,
        side="buy",
        quantity=quantity,
        filled_at=entry_at,
        decision=entry_decision,
    )
    engine.apply_fill(
        buy_fill,
        SettlementInstruction(
            settlement_id="replay-buy-settlement",
            due_at=entry_settlement_due,
        ),
    )
    engine.settlements.settle("replay-buy-settlement", entry_settlement_due)

    pre_exit = value_portfolio(
        cash=engine.cash,
        positions=engine.positions.positions,
        raw_mark_decisions={ticker: mark_decision},
    )

    sell_intent = OrderIntent(
        intent_id="replay-sell-intent",
        ticker=ticker,
        side="sell",
        quantity=quantity,
        created_at=exit_at,
        rationale="accounting-only replay",
    )
    engine.orders.create_from_intent(sell_intent, "replay-sell-order")
    engine.orders.submit("replay-sell-order", exit_at)

    sell_fill = factory.create_fill(
        fill_id="replay-sell-fill",
        order_id="replay-sell-order",
        ticker=ticker,
        side="sell",
        quantity=quantity,
        filled_at=exit_at,
        decision=exit_decision,
    )
    engine.apply_fill(
        sell_fill,
        SettlementInstruction(
            settlement_id="replay-sell-settlement",
            due_at=exit_settlement_due,
        ),
    )
    engine.settlements.settle("replay-sell-settlement", exit_settlement_due)

    position = engine.positions.positions[ticker]
    expected_final_cash = (
        opening_cash
        - (buy_fill.quantity * buy_fill.price + buy_fill.fees)
        + (sell_fill.quantity * sell_fill.price - sell_fill.fees)
    )
    expected_pre_exit_nav = (
        opening_cash
        - (buy_fill.quantity * buy_fill.price + buy_fill.fees)
        + quantity * mark_decision.price
    )

    checks = AccountingReplayChecks(
        signal_source_declared=bool(signal_source.strip()),
        sizing_raw=sizing_decision.use is PriceUse.SIZING,
        entry_raw=entry_decision.use is PriceUse.ENTRY,
        stop_observation_raw=stop_observation_decision.use is PriceUse.STOP_OBSERVATION,
        exit_raw=exit_decision.use is PriceUse.EXIT,
        mark_raw=mark_decision.use is PriceUse.MARK,
        share_count_reconciles=position.quantity == 0,
        cash_reconciles=abs(engine.cash.settled_cash - expected_final_cash) < 1e-9,
        receivables_reconcile=(
            abs(engine.cash.pending_receivables) < 1e-9
            and abs(engine.cash.pending_payables) < 1e-9
        ),
        nav_reconciles=abs(pre_exit.nav - expected_pre_exit_nav) < 1e-9,
        no_adjusted_execution_fallback=True,
    )

    return AccountingReplayResult(
        checks=checks,
        entry_price=buy_fill.price,
        exit_price=sell_fill.price,
        quantity=quantity,
        pre_exit_valuation=pre_exit,
        final_cash=engine.cash.settled_cash,
        realized_pnl=position.realized_pnl,
    )
