import pandas as pd
import pytest

from astraquant.research.component_registry import UnsupportedComponentError
from astraquant.research.feature_cache import FeatureCache
from astraquant.research.signal_engine import SignalCompiler, SignalContext
from astraquant.research.strategy_config import ComponentSpec, SignalConfig
from astraquant.research.technical_components import (
    gap_up,
    volume_spike,
)


def _panel(n=30):
    rows = []
    for i in range(n):
        rows.append(
            {
                "date": pd.Timestamp("2026-01-01") + pd.Timedelta(days=i),
                "stock_id": "2330",
                "open": 100.0 + i,
                "max": 101.0 + i,
                "min": 99.0 + i,
                "close": 100.0 + i,
                "Trading_Volume": 100.0,
            }
        )
    return pd.DataFrame(rows)


def test_volume_spike_uses_prior_average_not_current_bar():
    panel = _panel(21)
    panel.loc[20, "Trading_Volume"] = 200.0
    result = volume_spike(
        panel=panel,
        spec=ComponentSpec(
            type="VOLUME_SPIKE",
            params={"lookback": 20, "multiplier": 1.5},
        ),
        cache=FeatureCache(),
        context=SignalContext(source_revision="fixture"),
    )
    assert not bool(result.iloc[19])
    assert bool(result.iloc[20])


def test_gap_unfilled_confirmation_is_rejected_until_availability_semantics_exist():
    with pytest.raises(UnsupportedComponentError, match="delayed-confirmation"):
        gap_up(
            panel=_panel(5),
            spec=ComponentSpec(
                type="GAP_UP",
                params={"threshold": 0.02, "unfilled_sessions": 3},
            ),
            cache=FeatureCache(),
            context=SignalContext(source_revision="fixture"),
        )


def test_default_trigger_registry_exposes_reusable_technical_components():
    names = set(SignalCompiler().triggers.names())
    assert {
        "N_SESSION_HIGH",
        "GAP_UP",
        "VOLUME_SPIKE",
        "MA_GOLDEN_CROSS",
        "MACD_CROSS_ABOVE_ZERO",
        "KD_LOW_ZONE_GOLDEN_CROSS",
        "RSI_CROSS",
        "BOLLINGER_UPPER_BREAK",
        "PULLBACK_RECLAIM",
        "CONSECUTIVE_UP_DAYS",
    }.issubset(names)


def test_rsi_is_available_as_filter_and_ranking_factor():
    compiler = SignalCompiler()
    cfg = SignalConfig(
        name="rsi_reuse",
        trigger=ComponentSpec(type="N_SESSION_HIGH", params={"lookback": 20}),
        filters=(ComponentSpec(type="RSI", params={"lookback": 14, "min": 50}),),
        ranking=(ComponentSpec(type="RSI", params={"lookback": 14}),),
    )
    plan = compiler.compile(cfg)
    assert len(plan.filters) == 1
    assert len(plan.rankings) == 1


def test_unknown_component_still_fails_at_compile_time():
    compiler = SignalCompiler()
    cfg = SignalConfig(
        name="not_ready",
        trigger=ComponentSpec(type="ICHIMOKU", params={"mode": "CLOUD_BREAK"}),
    )
    with pytest.raises(UnsupportedComponentError, match="ICHIMOKU"):
        compiler.compile(cfg)
