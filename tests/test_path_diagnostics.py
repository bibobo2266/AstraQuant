from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from astraquant.portfolio.corporate_actions import (
    CashEntitlementBasis,
    CorporateActionEvent,
    CorporateActionType,
)
from astraquant.portfolio.historical_runner import HistoricalCorporateActionInstruction
from astraquant.portfolio.models import SecurityConversionLeg
from astraquant.research.path_diagnostics import (
    OrderState,
    PathDirection,
    PathStatus,
    PriceLimitObservation,
    RawBar,
    count_limit_states,
    directional_extrema,
    evaluate_ca_aware_unit_path,
)


def _bar(day, *, open_, high, low, close):
    return RawBar(
        ticker="2330",
        session=pd.Timestamp(day),
        open=open_,
        high=high,
        low=low,
        close=close,
        observed_trade=True,
        valid_ohlc=True,
    )


def test_long_directional_extrema_use_first_day_and_same_day_unknown():
    mfe, mae, d_mfe, d_mae, state = directional_extrema(
        [1.10, 1.10, 1.05],
        [0.90, 0.90, 0.95],
        direction=PathDirection.LONG,
    )
    assert mfe == pytest.approx(0.10)
    assert mae == pytest.approx(-0.10)
    assert d_mfe == 1
    assert d_mae == 1
    assert state is OrderState.SAME_DAY_UNKNOWN


def test_short_directional_extrema_follow_inverse_definition():
    mfe, mae, d_mfe, d_mae, state = directional_extrema(
        [1.05, 1.02],
        [0.95, 0.90],
        direction=PathDirection.SHORT,
    )
    assert mfe == pytest.approx(0.10)
    assert mae == pytest.approx(-0.05)
    assert d_mfe == 2
    assert d_mae == 1
    assert state is OrderState.MAE_FIRST


def test_limit_flags_use_supplied_daily_limits_only():
    bars = [
        _bar("2021-01-04", open_=100, high=110, low=90, close=110),
        _bar("2021-01-05", open_=100, high=100, low=100, close=100),
        _bar("2021-01-06", open_=100, high=105, low=95, close=100),
    ]
    limits = [
        PriceLimitObservation(upper=110, lower=90, known=True),
        PriceLimitObservation(upper=100, lower=90, known=True),
        PriceLimitObservation(no_limit=True, known=True),
    ]
    out = count_limit_states(bars, limits)
    assert out["limit_touch_up_days"] == 2
    assert out["limit_touch_down_days"] == 1
    assert out["limit_close_up_days"] == 2
    assert out["limit_close_down_days"] == 0
    assert out["all_trade_at_limit_days"] == 1
    assert out["no_price_limit_days"] == 1
    assert out["limit_price_unknown_days"] == 0


def test_ca_aware_unit_path_includes_cash_and_share_mutation():
    sessions = pd.bdate_range("2021-01-04", periods=5)
    bars = {
        ("2330", sessions[0]): _bar(
            sessions[0], open_=100, high=110, low=90, close=100
        ),
        ("2330", sessions[1]): _bar(
            sessions[1], open_=90, high=100, low=80, close=90
        ),
        ("2330", sessions[2]): _bar(
            sessions[2], open_=55, high=60, low=50, close=55
        ),
        ("2330", sessions[3]): _bar(
            sessions[3], open_=55, high=56, low=54, close=55
        ),
        ("2330", sessions[4]): _bar(
            sessions[4], open_=55, high=55, low=55, close=55
        ),
    }
    dividend = HistoricalCorporateActionInstruction(
        event=CorporateActionEvent(
            event_id="cash",
            ticker="2330",
            event_type=CorporateActionType.CASH_DIVIDEND,
            effective_at=datetime(2021, 1, 5),
            cash_per_share=10.0,
        ),
        applied_at=datetime(2021, 1, 5),
        cash_share_basis_mode=CashEntitlementBasis.OPENING_POSITION,
    )
    split = HistoricalCorporateActionInstruction(
        event=CorporateActionEvent(
            event_id="split",
            ticker="2330",
            event_type=CorporateActionType.SPLIT,
            effective_at=datetime(2021, 1, 6),
            share_multiplier=2.0,
        ),
        applied_at=datetime(2021, 1, 6),
    )
    result = evaluate_ca_aware_unit_path(
        sessions=sessions,
        entry_ticker="2330",
        entry_ref=100.0,
        direction=PathDirection.LONG,
        bars=bars,
        price_limits={},
        open_events_by_day={
            sessions[1]: (dividend,),
            sessions[2]: (split,),
        },
        close_events_by_day={},
        terminal_stale_windows={},
        prior_valid_close={},
    )
    assert result.status is PathStatus.OK
    assert result.raw_mfe == pytest.approx(0.30)
    assert result.raw_mae == pytest.approx(-0.10)
    assert result.days_to_mfe == 3
    assert result.days_to_mae == 1
    assert result.order_state is OrderState.MAE_FIRST


def test_no_valid_entry_ref_is_explicit():
    result = evaluate_ca_aware_unit_path(
        sessions=pd.bdate_range("2021-01-04", periods=5),
        entry_ticker="2330",
        entry_ref=np.nan,
        direction=PathDirection.LONG,
        bars={},
        price_limits={},
        open_events_by_day={},
        close_events_by_day={},
        terminal_stale_windows={},
        prior_valid_close={},
    )
    assert result.status is PathStatus.NO_VALID_ENTRY_REF


def test_multi_leg_successor_intraday_path_is_unresolved():
    sessions = pd.bdate_range("2021-01-04", periods=5)
    bars = {
        ("2330", day): _bar(
            day, open_=100, high=101, low=99, close=100
        )
        for day in sessions
    }
    event = HistoricalCorporateActionInstruction(
        event=CorporateActionEvent(
            event_id="multi",
            ticker="2330",
            event_type=CorporateActionType.MERGER,
            effective_at=datetime(2021, 1, 5),
        ),
        applied_at=datetime(2021, 1, 5),
        successor_legs=(
            SecurityConversionLeg(
                to_ticker="1111",
                quantity_multiplier=1.0,
                value_weight=0.5,
            ),
            SecurityConversionLeg(
                to_ticker="2222",
                quantity_multiplier=1.0,
                value_weight=0.5,
            ),
        ),
    )
    result = evaluate_ca_aware_unit_path(
        sessions=sessions,
        entry_ticker="2330",
        entry_ref=100.0,
        direction=PathDirection.LONG,
        bars=bars,
        price_limits={},
        open_events_by_day={sessions[1]: (event,)},
        close_events_by_day={},
        terminal_stale_windows={},
        prior_valid_close={},
    )
    assert result.status is PathStatus.MULTI_LEG_INTRADAY_UNRESOLVED
    assert result.terminal_event is True


def test_anchor_down_short_direction_manual_check():
    mfe, mae, d_mfe, d_mae, state = directional_extrema(
        [1.10, 1.05, 0.95],
        [0.98, 0.90, 0.80],
        direction=PathDirection.SHORT,
    )
    assert mfe == pytest.approx(0.20)
    assert mae == pytest.approx(-0.10)
    assert d_mfe == 3
    assert d_mae == 1
    assert state is OrderState.MAE_FIRST
