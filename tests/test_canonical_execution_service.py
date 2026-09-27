from datetime import date, datetime

import pandas as pd
import pytest

from astraquant.data.market_coordinates import PriceUse, SignalPriceSemantics
from astraquant.data.source_adapter import SourceDataAdapter
from astraquant.execution.assumptions import FixedBpsSlippage, ZeroFeeModel
from astraquant.execution.fills import ExecutionFillFactory, NotExecutableError
from astraquant.execution.market_data import ExecutionAvailability, ExecutionMarketData
from astraquant.execution.service import CanonicalExecutionService, SignalDeclaration
from astraquant.portfolio.engine import PortfolioEngine, SettlementInstruction
from astraquant.portfolio.models import OrderIntent


def _service(tmp_path, *, buy_blocked=False):
    root = tmp_path / "source"
    (root / "raw").mkdir(parents=True)
    (root / "reference").mkdir(parents=True)

    pd.DataFrame([
        {
            "date": "2026-09-24",
            "stock_id": "2330",
            "open": 100.0,
            "max": 110.0,
            "min": 95.0,
            "close": 105.0,
        }
    ]).to_parquet(root / "raw" / "prices_raw_2026.parquet", index=False)

    pd.DataFrame([
        {
            "date": "2026-09-24",
            "stock_id": "2330",
            "observed_trade": True,
            "valid_ohlc": True,
            "buy_blocked": buy_blocked,
            "sell_blocked": False,
            "reason": "LOCKED_LIMIT_UP" if buy_blocked else "OBSERVED",
        }
    ]).to_parquet(root / "reference" / "tradability.parquet", index=False)

    market = ExecutionMarketData(SourceDataAdapter(root))
    factory = ExecutionFillFactory(
        fee_model=ZeroFeeModel(),
        slippage_model=FixedBpsSlippage(bps=0),
    )
    portfolio = PortfolioEngine(opening_cash=100000.0)
    service = CanonicalExecutionService(
        market_data=market,
        fill_factory=factory,
        portfolio=portfolio,
    )
    return service, portfolio


def _signal():
    return SignalDeclaration(
        source="declared adjusted research signal",
        price_semantics=SignalPriceSemantics.SCALE_INVARIANT,
    )


def test_canonical_service_executes_entry_from_raw(tmp_path):
    service, portfolio = _service(tmp_path)
    intent = OrderIntent(
        intent_id="I1",
        ticker="2330",
        side="buy",
        quantity=10,
        created_at=datetime(2026, 9, 24, 9, 0),
        rationale="test",
    )

    out = service.execute(
        intent=intent,
        signal=_signal(),
        order_id="O1",
        fill_id="F1",
        submitted_at=datetime(2026, 9, 24, 9, 0),
        session_date=date(2026, 9, 24),
        use=PriceUse.ENTRY,
        field="open",
        settlement=SettlementInstruction(
            settlement_id="S1",
            due_at=datetime(2026, 9, 26),
        ),
    )

    assert out.fill.price == 100.0
    assert out.raw_decision.use is PriceUse.ENTRY
    assert portfolio.positions.positions["2330"].quantity == 10
    assert portfolio.cash.pending_payables == 1000.0


def test_non_executable_intent_does_not_create_order_or_position(tmp_path):
    service, portfolio = _service(tmp_path, buy_blocked=True)
    intent = OrderIntent(
        intent_id="I1",
        ticker="2330",
        side="buy",
        quantity=10,
        created_at=datetime(2026, 9, 24, 9, 0),
        rationale="test",
    )

    with pytest.raises(NotExecutableError, match="LOCKED_LIMIT_UP"):
        service.execute(
            intent=intent,
            signal=_signal(),
            order_id="O1",
            fill_id="F1",
            submitted_at=datetime(2026, 9, 24, 9, 0),
            session_date=date(2026, 9, 24),
            use=PriceUse.ENTRY,
            field="open",
            settlement=SettlementInstruction(
                settlement_id="S1",
                due_at=datetime(2026, 9, 26),
            ),
        )

    assert "O1" not in portfolio.orders.orders
    assert "2330" not in portfolio.positions.positions
    assert portfolio.cash.pending_payables == 0.0


def test_service_raw_sizing_stop_and_mark(tmp_path):
    service, _ = _service(tmp_path)

    sizing = service.sizing_price(
        ticker="2330",
        session_date=date(2026, 9, 24),
        side="buy",
        field="open",
        signal=_signal(),
    )
    stop = service.stop_observation(
        ticker="2330",
        session_date=date(2026, 9, 24),
        side="sell",
    )
    mark = service.mark(
        ticker="2330",
        session_date=date(2026, 9, 24),
    )

    assert sizing.availability is ExecutionAvailability.EXECUTABLE
    assert sizing.use is PriceUse.SIZING
    assert sizing.price == 100.0
    assert stop.use is PriceUse.STOP_OBSERVATION
    assert stop.price == 95.0
    assert mark.use is PriceUse.MARK
    assert mark.price == 105.0


def test_signal_source_must_be_declared():
    with pytest.raises(ValueError, match="signal source"):
        SignalDeclaration(
            source="",
            price_semantics=SignalPriceSemantics.SCALE_INVARIANT,
        )


def test_buy_overcommit_is_blocked_before_state_mutation(tmp_path):
    service, portfolio = _service(tmp_path)
    intent = OrderIntent(
        intent_id="I-CASH",
        ticker="2330",
        side="buy",
        quantity=2000,
        created_at=datetime(2026, 9, 24, 9, 0),
        rationale="cash guard",
    )

    with pytest.raises(NotExecutableError, match="available_to_commit"):
        service.execute(
            intent=intent,
            signal=_signal(),
            order_id="O-CASH",
            fill_id="F-CASH",
            submitted_at=datetime(2026, 9, 24, 9, 0),
            session_date=date(2026, 9, 24),
            use=PriceUse.ENTRY,
            field="open",
            settlement=SettlementInstruction(
                settlement_id="S-CASH",
                due_at=datetime(2026, 9, 26),
            ),
        )

    assert "O-CASH" not in portfolio.orders.orders
    assert "2330" not in portfolio.positions.positions
    assert portfolio.cash.pending_payables == 0.0


def test_canonical_service_executes_raw_stop_fill(tmp_path):
    service, portfolio = _service(tmp_path)
    entry_intent = OrderIntent(
        intent_id="I-ENTRY",
        ticker="2330",
        side="buy",
        quantity=10,
        created_at=datetime(2026, 9, 24, 9, 0),
        rationale="seed position",
    )
    service.execute(
        intent=entry_intent,
        signal=_signal(),
        order_id="O-ENTRY",
        fill_id="F-ENTRY",
        submitted_at=datetime(2026, 9, 24, 9, 0),
        session_date=date(2026, 9, 24),
        use=PriceUse.ENTRY,
        field="open",
        settlement=SettlementInstruction(
            settlement_id="S-ENTRY",
            due_at=datetime(2026, 9, 26),
        ),
    )

    stop_intent = OrderIntent(
        intent_id="I-STOP",
        ticker="2330",
        side="sell",
        quantity=10,
        created_at=datetime(2026, 9, 24, 13, 0),
        rationale="raw stop",
    )
    out = service.execute_stop(
        intent=stop_intent,
        signal=_signal(),
        order_id="O-STOP",
        fill_id="F-STOP",
        submitted_at=datetime(2026, 9, 24, 13, 0),
        session_date=date(2026, 9, 24),
        stop_price=97.0,
        settlement=SettlementInstruction(
            settlement_id="S-STOP",
            due_at=datetime(2026, 9, 26),
        ),
    )

    assert out.raw_decision.use is PriceUse.STOP_FILL
    assert out.fill.price == 97.0
    assert portfolio.positions.positions["2330"].quantity == 0
