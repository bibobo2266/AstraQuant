import numpy as np
import pandas as pd
import pytest

from astraquant.research.baseline_60d_breakout import (
    ATR_MULTIPLIER,
    ATR_PERIOD,
    BREAK_LOW_WINDOW,
    atr14_sma_from_true_range,
    atr_from_entry_stop_level,
    atr_from_entry_stop_trigger,
    break_n_day_low_trigger,
)
from astraquant.research.component_registry import UnsupportedComponentError
from astraquant.research.exit_engine import ExitCompiler
from astraquant.research.strategy_config import ComponentSpec, ExitConfig, ExitRuleConfig
from astraquant.research.technical_components import column_threshold


def test_baseline_constants_are_frozen_to_source_translation():
    assert ATR_PERIOD == 14
    assert ATR_MULTIPLIER == 3.0
    assert BREAK_LOW_WINDOW == 20


def test_atr14_uses_daily_simple_moving_average_not_wilder():
    tr = pd.Series(np.arange(1.0, 16.0))
    atr = atr14_sma_from_true_range(tr)

    assert pd.isna(atr.iloc[12])
    assert atr.iloc[13] == pytest.approx(np.mean(np.arange(1.0, 15.0)))
    assert atr.iloc[14] == pytest.approx(np.mean(np.arange(2.0, 16.0)))
    wilder_second = ((13 * atr.iloc[13]) + 15.0) / 14.0
    assert atr.iloc[14] != pytest.approx(wilder_second)


def test_atr_stop_is_anchored_to_entry_and_can_move_both_directions_with_atr():
    entry = 100.0
    levels = [atr_from_entry_stop_level(entry, x) for x in (2.0, 4.0, 1.0)]
    assert levels == pytest.approx([94.0, 88.0, 97.0])
    assert atr_from_entry_stop_trigger(close=94.0, entry_anchor=entry, atr_value=2.0)
    assert atr_from_entry_stop_trigger(close=93.0, entry_anchor=entry, atr_value=2.0)
    assert not atr_from_entry_stop_trigger(close=95.0, entry_anchor=entry, atr_value=2.0)
    assert pd.isna(
        atr_from_entry_stop_trigger(close=None, entry_anchor=entry, atr_value=2.0)
    )


def test_break_n_day_low_uses_strict_less_than_and_preserves_missing():
    assert not break_n_day_low_trigger(close=90.0, prior_low_reference=90.0)
    assert break_n_day_low_trigger(close=89.99, prior_low_reference=90.0)
    assert pd.isna(break_n_day_low_trigger(close=np.nan, prior_low_reference=90.0))


def test_ma120_and_prior20_amount_reuse_column_threshold_without_new_filter():
    panel = pd.DataFrame(
        {
            "close_to_ma120": [-0.01, 0.0, 0.02, np.nan],
            "prior20_amount_twd": [19_999_999.0, 20_000_000.0, 30_000_000.0, np.nan],
        }
    )
    ma = column_threshold(
        panel=panel,
        spec=ComponentSpec(
            type="COLUMN_THRESHOLD",
            params={"column": "close_to_ma120", "min": 0.0},
        ),
        cache=None,
        context=None,
    )
    liquidity = column_threshold(
        panel=panel,
        spec=ComponentSpec(
            type="COLUMN_THRESHOLD",
            params={"column": "prior20_amount_twd", "min": 20_000_000.0},
        ),
        cache=None,
        context=None,
    )
    assert ma.tolist() == [False, True, True, False]
    assert liquidity.tolist() == [False, True, True, False]


@pytest.mark.parametrize("exit_type", ["ATR_FROM_ENTRY_STOP", "BREAK_N_DAY_LOW"])
def test_unwired_baseline_exit_types_remain_fail_closed(exit_type):
    config = ExitConfig(
        name="baseline_60d_prep_only",
        rules=(ExitRuleConfig(type=exit_type, params={}),),
    )
    with pytest.raises(UnsupportedComponentError, match=exit_type):
        ExitCompiler().compile(config)
