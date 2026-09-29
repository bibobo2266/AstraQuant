import numpy as np
import pandas as pd

from astraquant.research.feature_cache import FeatureCache
from astraquant.research.signal_engine import SignalCompiler, SignalContext
from astraquant.research.strategy_config import ComponentSpec, SignalConfig
from astraquant.research.technical_components import long_term_trend_structure


def _trend_panel(n=230):
    return pd.DataFrame(
        {
            "date": pd.bdate_range("2025-01-02", periods=n),
            "stock_id": ["2330"] * n,
            "close": np.linspace(100.0, 200.0, n),
        }
    )


def test_oneil_long_term_structure_accepts_rising_50_200_alignment():
    panel = _trend_panel()
    spec = ComponentSpec(
        type="LONG_TERM_TREND_STRUCTURE",
        params={
            "fast_sessions": 50,
            "slow_sessions": 200,
            "slope_lookback_sessions": 10,
            "min_fast_slow_spread": 0.02,
            "max_fast_slow_spread": 0.50,
        },
    )
    result = long_term_trend_structure(
        panel=panel,
        spec=spec,
        cache=FeatureCache(),
        context=SignalContext(source_revision="fixture"),
    )
    assert bool(result.iloc[-1])


def test_oneil_long_term_structure_spread_cap_is_configurable():
    panel = _trend_panel()
    spec = ComponentSpec(
        type="LONG_TERM_TREND_STRUCTURE",
        params={
            "fast_sessions": 50,
            "slow_sessions": 200,
            "slope_lookback_sessions": 10,
            "min_fast_slow_spread": 0.0,
            "max_fast_slow_spread": 0.01,
        },
    )
    result = long_term_trend_structure(
        panel=panel,
        spec=spec,
        cache=FeatureCache(),
        context=SignalContext(source_revision="fixture"),
    )
    assert not bool(result.iloc[-1])


def test_oneil_filter_is_registered_as_filter_not_trigger():
    compiler = SignalCompiler()
    config = SignalConfig(
        name="high_with_oneil_structure",
        trigger=ComponentSpec(type="N_SESSION_HIGH", params={"lookback": 20}),
        filters=(
            ComponentSpec(
                type="LONG_TERM_TREND_STRUCTURE",
                params={"fast_sessions": 50, "slow_sessions": 200},
            ),
        ),
    )
    plan = compiler.compile(config)
    assert len(plan.filters) == 1
