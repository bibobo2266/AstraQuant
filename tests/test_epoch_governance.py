from datetime import date, datetime, timezone
from decimal import Decimal

import pandas as pd
import pytest

from astraquant.research.epoch_governance import (
    E2_LABEL_TW,
    E3EffectQueryBlocked,
    E4RegistrationError,
    Epoch,
    EpochGovernanceError,
    QueryKind,
    StrategyVersionRecord,
    assert_legacy_breakout_nav_regression,
    authorize_query,
    epoch_for_date,
    legacy_breakout_nav_regression_matches,
    purge_path_windows,
    resolve_effect_period,
    resolve_historical_effect_period,
)


def _record(**overrides):
    values = dict(
        strategy_version="strategy-v1",
        frozen_at=None,
        validation_start_date=None,
        entry_rules="entry",
        exit_rules="exit",
        parameters="params",
        universe_rules="universe",
        market_context_rules="market",
        cost_assumptions="cost",
        capital_rules="capital",
        validation_length=None,
        validation_criteria=None,
    )
    values.update(overrides)
    return StrategyVersionRecord(**values)


def test_e1_is_default_and_e2_requires_explicit_epoch_selection():
    record = _record()
    assert resolve_effect_period(record).epoch is Epoch.E1
    e2 = resolve_historical_effect_period("E2")
    assert e2.epoch is Epoch.E2
    assert e2.label == E2_LABEL_TW


def test_e3_effect_is_blocked_but_data_quality_is_allowed():
    record = _record()
    with pytest.raises(E3EffectQueryBlocked):
        authorize_query(
            record,
            start=date(2026, 7, 1),
            end=date(2026, 7, 7),
            kind=QueryKind.EFFECT,
        )
    epochs = authorize_query(
        record,
        start=date(2026, 7, 1),
        end=date(2026, 7, 7),
        kind=QueryKind.DATA_QUALITY,
    )
    assert epochs == (Epoch.E3,)


def test_e4_boundary_is_strategy_version_specific():
    a = _record(
        strategy_version="A",
        frozen_at=datetime(2026, 7, 10, 8, 0, tzinfo=timezone.utc),
        validation_start_date=date(2026, 7, 11),
        validation_length="preregistered duration",
        validation_criteria="preregistered criteria",
    )
    b = _record(strategy_version="B")
    assert epoch_for_date(a, date(2026, 7, 12)) is Epoch.E4
    assert epoch_for_date(b, date(2026, 7, 12)) is Epoch.E3


def test_e4_requires_preregistered_length_and_criteria():
    incomplete = _record(
        frozen_at=datetime(2026, 7, 10, 8, 0, tzinfo=timezone.utc),
        validation_start_date=date(2026, 7, 11),
    )
    with pytest.raises(E4RegistrationError):
        resolve_effect_period(incomplete, "E4")


def test_path_window_purge_counts_cross_boundary_without_shortening():
    sessions = pd.bdate_range("2021-12-20", "2022-01-14")
    candidates = pd.DataFrame(
        {
            "date": [pd.Timestamp("2021-12-20"), pd.Timestamp("2021-12-29")],
            "stock_id": ["2330", "2317"],
        }
    )
    result = purge_path_windows(
        candidates,
        trading_sessions=sessions,
        period_start=date(2016, 1, 4),
        period_end=date(2021, 12, 31),
        window_sessions=5,
    )
    assert list(result.included["stock_id"]) == ["2330"]
    assert result.cross_boundary_count == 1
    assert result.unavailable_endpoint_count == 0


def test_path_window_only_allows_governed_5_10_20_lengths():
    with pytest.raises(ValueError, match="5/10/20"):
        purge_path_windows(
            pd.DataFrame({"date": [pd.Timestamp("2021-01-04")]}),
            trading_sessions=pd.bdate_range("2021-01-04", periods=30),
            period_start=date(2016, 1, 4),
            period_end=date(2021, 12, 31),
            window_sessions=7,
        )


def test_legacy_regression_exemption_is_boolean_or_difference_only():
    assert legacy_breakout_nav_regression_matches(Decimal("51696620.30")) is True
    assert legacy_breakout_nav_regression_matches(Decimal("51696620.29")) is False
    with pytest.raises(EpochGovernanceError) as exc:
        assert_legacy_breakout_nav_regression(Decimal("51696619.30"))
    assert str(exc.value) == "回歸失敗；差異金額：1.00"
