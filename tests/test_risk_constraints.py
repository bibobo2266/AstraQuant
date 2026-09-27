from astraquant.risk.constraints import (
    MaxPositionCountConstraint,
    RiskContext,
    evaluate_constraints,
)


def test_max_position_constraint_blocks_new_position_at_limit():
    context = RiskContext(
        symbol="2330",
        side="buy",
        quantity=10,
        portfolio_state={
            "position_count": 5,
            "opening_new_position": True,
        },
    )
    results = evaluate_constraints(
        [MaxPositionCountConstraint(max_positions=5)],
        context,
    )
    assert not results[0].passed


def test_existing_position_not_blocked_by_position_count_rule():
    context = RiskContext(
        symbol="2330",
        side="buy",
        quantity=10,
        portfolio_state={
            "position_count": 5,
            "opening_new_position": False,
        },
    )
    result = MaxPositionCountConstraint(max_positions=5).evaluate(context)
    assert result.passed
