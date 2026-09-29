from pathlib import Path

import pytest

from astraquant.research.config_io import (
    load_exit_config,
    load_run_config,
    load_signal_config,
    load_universe_config,
)
from astraquant.research.exit_engine import ExitCompiler


@pytest.mark.parametrize(
    "run_path, expected_signal",
    [
        (
            "configs/research/runs/vcp_all_liquid_stop12_time250.yaml",
            "vcp_breakout",
        ),
        (
            "configs/research/runs/rsi_pullback_reclaim_all_liquid_stop12_time250.yaml",
            "rsi_pullback_reclaim",
        ),
    ],
)
def test_source_performance_run_configs_resolve_and_keep_frozen_exit_layer(
    run_path,
    expected_signal,
):
    root = Path(__file__).resolve().parents[1]
    run = load_run_config(root / run_path)
    universe = load_universe_config(root / run.universe)
    signal = load_signal_config(root / run.signal)
    exit_cfg = load_exit_config(root / run.exit)

    assert universe.name == "all_liquid"
    assert signal.name == expected_signal
    compiled = ExitCompiler().compile(exit_cfg)
    assert compiled.stop_fraction == 0.12
    assert compiled.max_hold_sessions == 250
