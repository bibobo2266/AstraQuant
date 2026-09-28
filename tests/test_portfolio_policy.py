from datetime import date

import pandas as pd

from astraquant.data.market_coordinates import PriceUse
from astraquant.execution.market_data import (
    ExecutionAvailability,
    ExecutionPriceDecision,
    RawExecutionBar,
    TradabilityState,
)
from astraquant.portfolio.corporate_actions import CorporateActionEvent, CorporateActionType
from astraquant.portfolio.policy import (
    CapacitySelectionRule,
    EntryCandidate,
    PortfolioIntentPolicy,
    PortfolioPolicyConfig,
)


def _sizing(ticker: str, price: float, *, executable: bool = True):
    bar = RawExecutionBar(
        ticker=ticker,
        session_date=date(2026, 1, 2),
        open=price,
        high=price,
        low=price,
        close=price,
    )
    trad = TradabilityState(
        ticker=ticker,
        session_date=date(2026, 1, 2),
        observed_trade=True,
        valid_ohlc=True,
        buy_blocked=not executable,
        sell_blocked=False,
        reason="OBSERVED" if executable else "BUY_BLOCKED",
    )
    return ExecutionPriceDecision(
        availability=(
            ExecutionAvailability.EXECUTABLE
            if executable
            else ExecutionAvailability.NOT_EXECUTABLE
        ),
        use=PriceUse.SIZING,
        side="buy",
        field="open",
        price=price if executable else None,
        reason="OK" if executable else "BUY_BLOCKED",
        bar=bar,
        tradability=trad,
    )


def test_board_lot_sizing_uses_raw_price_and_budget():
    policy = PortfolioIntentPolicy(
        PortfolioPolicyConfig(
            position_fraction=0.10,
            max_positions=10,
            lot_size=1000,
            random_seed=7,
        )
    )

    planned, skipped = policy.plan_entries(
        candidates=[EntryCandidate("2330", _sizing("2330", 50.0))],
        session_index=100,
        current_nav=1_000_000.0,
        available_cash=1_000_000.0,
    )

    assert skipped == {}
    assert len(planned) == 1
    assert planned[0].quantity == 2000
    assert planned[0].raw_sizing_price == 50.0


def test_board_lot_unaffordable_candidate_is_skipped():
    policy = PortfolioIntentPolicy(
        PortfolioPolicyConfig(position_fraction=0.10, max_positions=10)
    )

    planned, skipped = policy.plan_entries(
        candidates=[EntryCandidate("2330", _sizing("2330", 200.0))],
        session_index=1,
        current_nav=1_000_000.0,
        available_cash=1_000_000.0,
    )

    assert planned == []
    assert skipped["2330"] == "BOARD_LOT_UNAFFORDABLE"


def test_reentry_gap_matches_legacy_strict_greater_than_rule():
    policy = PortfolioIntentPolicy(
        PortfolioPolicyConfig(
            position_fraction=0.10,
            max_positions=10,
            reentry_gap_sessions=20,
        )
    )
    policy.register_entry(
        ticker="2330",
        quantity=1000,
        fill_price=100.0,
        session_index=10,
    )
    policy.register_exit("2330")

    assert not policy.eligible_for_reentry("2330", 30)
    assert policy.eligible_for_reentry("2330", 31)


def test_stop_and_max_hold_state_is_recorded_from_actual_fill():
    policy = PortfolioIntentPolicy(
        PortfolioPolicyConfig(
            position_fraction=0.10,
            max_positions=10,
            stop_fraction=0.12,
            max_hold_sessions=250,
        )
    )
    state = policy.register_entry(
        ticker="2330",
        quantity=1000,
        fill_price=100.0,
        session_index=5,
    )

    assert state.stop_price == 88.0
    assert not policy.max_hold_due("2330", 254)
    assert policy.max_hold_due("2330", 255)


def test_capacity_selection_is_reproducible_for_same_seed():
    candidates = [
        EntryCandidate(str(1000 + i), _sizing(str(1000 + i), 10.0))
        for i in range(6)
    ]
    config = PortfolioPolicyConfig(
        position_fraction=0.10,
        max_positions=2,
        random_seed=123,
    )
    first = PortfolioIntentPolicy(config)
    second = PortfolioIntentPolicy(config)

    p1, s1 = first.plan_entries(
        candidates=candidates,
        session_index=1,
        current_nav=1_000_000.0,
        available_cash=1_000_000.0,
    )
    p2, s2 = second.plan_entries(
        candidates=candidates,
        session_index=1,
        current_nav=1_000_000.0,
        available_cash=1_000_000.0,
    )

    assert [x.ticker for x in p1] == [x.ticker for x in p2]
    assert s1 == s2
    assert len(p1) == 2


def test_non_executable_sizing_is_skipped():
    policy = PortfolioIntentPolicy(
        PortfolioPolicyConfig(position_fraction=0.10, max_positions=10)
    )

    planned, skipped = policy.plan_entries(
        candidates=[
            EntryCandidate(
                "2330",
                _sizing("2330", 100.0, executable=False),
            )
        ],
        session_index=1,
        current_nav=1_000_000.0,
        available_cash=1_000_000.0,
    )

    assert planned == []
    assert skipped["2330"] == "NOT_EXECUTABLE_SIZING"


def test_policy_stop_is_adjusted_for_split_and_cash_entitlement():
    policy = PortfolioIntentPolicy(
        PortfolioPolicyConfig(
            position_fraction=0.10,
            max_positions=10,
            stop_fraction=0.12,
        )
    )
    policy.register_entry(
        ticker="2330",
        quantity=100,
        fill_price=100.0,
        session_index=1,
    )

    policy.apply_corporate_action(
        CorporateActionEvent(
            event_id="CA1",
            ticker="2330",
            event_type=CorporateActionType.CAPITAL_REDUCTION,
            effective_at=pd.Timestamp("2026-01-05").to_pydatetime(),
            share_multiplier=0.5,
            cash_per_share=10.0,
        )
    )

    state = policy.managed_positions["2330"]
    assert state.quantity == 50
    assert state.entry_price == 200.0
    assert state.stop_price == 156.0


def test_policy_cash_dividend_reduces_raw_stop_without_changing_quantity():
    policy = PortfolioIntentPolicy(
        PortfolioPolicyConfig(
            position_fraction=0.10,
            max_positions=10,
            stop_fraction=0.12,
        )
    )
    policy.register_entry(
        ticker="2330",
        quantity=100,
        fill_price=100.0,
        session_index=1,
    )

    policy.apply_corporate_action(
        CorporateActionEvent(
            event_id="DIV1",
            ticker="2330",
            event_type=CorporateActionType.CASH_DIVIDEND,
            effective_at=pd.Timestamp("2026-01-05").to_pydatetime(),
            cash_per_share=5.0,
        )
    )

    state = policy.managed_positions["2330"]
    assert state.quantity == 100
    assert state.entry_price == 100.0
    assert state.stop_price == 83.0


def test_deterministic_capacity_rules_use_prespecified_metadata():
    candidates = [
        EntryCandidate("1003", _sizing("1003", 10.0), signal_date="2026-01-02", turnover_value=300.0, breakout_excess=0.03),
        EntryCandidate("1001", _sizing("1001", 10.0), signal_date="2026-01-02", turnover_value=100.0, breakout_excess=0.01),
        EntryCandidate("1002", _sizing("1002", 10.0), signal_date="2026-01-02", turnover_value=200.0, breakout_excess=0.05),
    ]
    expected = {
        CapacitySelectionRule.TICKER_ASC: ["1001"],
        CapacitySelectionRule.TURNOVER_DESC: ["1003"],
        CapacitySelectionRule.TURNOVER_ASC: ["1001"],
        CapacitySelectionRule.BREAKOUT_EXCESS_DESC: ["1002"],
        CapacitySelectionRule.BREAKOUT_EXCESS_ASC: ["1001"],
    }
    for rule, tickers in expected.items():
        policy = PortfolioIntentPolicy(
            PortfolioPolicyConfig(
                position_fraction=0.10,
                max_positions=1,
                capacity_selection_rule=rule,
            )
        )
        planned, skipped = policy.plan_entries(
            candidates=candidates,
            session_index=1,
            current_nav=1_000_000.0,
            available_cash=1_000_000.0,
        )
        assert [x.ticker for x in planned] == tickers
        assert sum(reason.startswith("CAPACITY_") for reason in skipped.values()) == 2


def test_hash_capacity_rule_is_reproducible_and_order_independent():
    candidates = [
        EntryCandidate(str(1000 + i), _sizing(str(1000 + i), 10.0), signal_date="2026-01-02")
        for i in range(6)
    ]
    config = PortfolioPolicyConfig(
        position_fraction=0.10,
        max_positions=2,
        capacity_selection_rule=CapacitySelectionRule.HASH_ASC,
    )
    first = PortfolioIntentPolicy(config)
    second = PortfolioIntentPolicy(config)
    p1, _ = first.plan_entries(
        candidates=candidates,
        session_index=1,
        current_nav=1_000_000.0,
        available_cash=1_000_000.0,
    )
    p2, _ = second.plan_entries(
        candidates=list(reversed(candidates)),
        session_index=1,
        current_nav=1_000_000.0,
        available_cash=1_000_000.0,
    )
    assert [x.ticker for x in p1] == [x.ticker for x in p2]
