from pathlib import Path

import numpy as np
import pandas as pd

from astraquant.portfolio.policy import PortfolioPolicyConfig
from astraquant.research.parameter_sweep import ResearchParameterSweepRunner
from astraquant.research.config_engine import ResearchConfigEngine
from astraquant.research.universe_engine import UniverseCompiler
from astraquant.research.signal_engine import SignalContext
from astraquant.research.universe_engine import UniverseContext


P2_SHA = "379d58f6a8aa06b1e020d56911930f4bc01861d3eeca109613d9e5b1e490d134"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _panel() -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-02", periods=260)
    rows = []
    for ticker, base, slope in [("2634", 40.0, 0.30), ("2330", 100.0, 0.20)]:
        for i, day in enumerate(dates):
            close = base + slope * i
            rows.append(
                {
                    "date": day,
                    "stock_id": ticker,
                    "close": close,
                    "Trading_money": 20_000_000.0 if ticker == "2634" else 30_000_000.0,
                    "observed_trade": True,
                    "valid_ohlc": True,
                }
            )
    return pd.DataFrame(rows)


def _configs(root: Path) -> Path:
    _write(
        root / "themes/軍工航太.yaml",
        """
schema_version: "1"
theme: 軍工航太
members:
  - ticker: "2634"
    from: 2024-01-02
    to: null
    source: "fixture evidence"
""",
    )
    _write(
        root / "configs/universes/all.yaml",
        f"""
schema_version: "1"
name: all
base:
  ticker_pattern: '^[1-9]\\d{{3}}$'
  min_close_twd: 10
  p2_060_exclusion_sha256: "{P2_SHA}"
pools:
  - type: ALL
    turnover_top_fraction: 1.0
""",
    )
    _write(
        root / "configs/universes/defense.yaml",
        f"""
schema_version: "1"
name: defense
base:
  ticker_pattern: '^[1-9]\\d{{3}}$'
  min_close_twd: 10
  p2_060_exclusion_sha256: "{P2_SHA}"
pools:
  - type: INDUSTRY_THEME
    groups:
      - mode: THEME
        themes: ["軍工航太"]
        combine: OR
""",
    )
    _write(
        root / "configs/signals/oneil.yaml",
        """
schema_version: "1"
name: oneil_high
trigger:
  type: N_SESSION_HIGH
  params:
    lookback: 20
filters:
  - type: LONG_TERM_TREND_STRUCTURE
    params:
      fast_sessions: 50
      slow_sessions: 200
      slope_lookback_sessions: 10
      min_fast_slow_spread: 0.0
      max_fast_slow_spread: null
ranking: []
""",
    )
    _write(
        root / "configs/exits/exit.yaml",
        """
schema_version: "1"
name: stop12_time250
rules:
  - type: FIXED_STOP_TARGET
    params: {stop_pct: 0.12, target_pct: null}
  - type: TIME_EXIT
    params: {sessions: 250}
""",
    )
    sweep = root / "configs/sweeps/oneil.yaml"
    _write(
        sweep,
        """
schema_version: "1"
name: oneil_taiwan
universes:
  - configs/universes/all.yaml
  - configs/universes/defense.yaml
signal: configs/signals/oneil.yaml
exit: configs/exits/exit.yaml
axes:
  - target: filter:LONG_TERM_TREND_STRUCTURE.fast_sessions
    values: [40, 50]
  - target: filter:LONG_TERM_TREND_STRUCTURE.slow_sessions
    values: [180, 200]
  - target: filter:LONG_TERM_TREND_STRUCTURE.slope_lookback_sessions
    values: [5, 10]
execution_assumptions_id: zero-cost
max_combinations: 100
report_trade_stats_first: true
""",
    )
    return sweep


def test_oneil_sweep_expands_parameter_surface_across_scopes(tmp_path):
    sweep = _configs(tmp_path)
    runner = ResearchParameterSweepRunner()
    result = runner.prepare_sweep(
        sweep_config_path=sweep,
        root=tmp_path,
        panel=_panel(),
        universe_context=UniverseContext(
            p2_060_excluded_tickers=frozenset(),
            p2_060_exclusion_sha256=P2_SHA,
            theme_root=tmp_path / "themes",
        ),
        signal_context=SignalContext(source_revision="fixture-v1"),
        base_policy=PortfolioPolicyConfig(
            position_fraction=0.10,
            max_positions=10,
        ),
    )

    assert len(result.runs) == 16
    assert len(result.summary) == 16
    assert set(result.summary["universe"]) == {"all", "defense"}
    assert result.summary["parameters"].str.contains("fast_sessions").all()
    assert result.feature_cache_hits > 0
    assert result.feature_cache_misses > 0


def test_theme_scope_is_narrower_than_all_scope(tmp_path):
    sweep = _configs(tmp_path)
    result = ResearchParameterSweepRunner().prepare_sweep(
        sweep_config_path=sweep,
        root=tmp_path,
        panel=_panel(),
        universe_context=UniverseContext(
            p2_060_excluded_tickers=frozenset(),
            p2_060_exclusion_sha256=P2_SHA,
            theme_root=tmp_path / "themes",
        ),
        signal_context=SignalContext(source_revision="fixture-v1"),
        base_policy=PortfolioPolicyConfig(
            position_fraction=0.10,
            max_positions=10,
        ),
    )
    counts = result.summary.groupby("universe")["universe_rows_counting"].max()
    assert counts["defense"] < counts["all"]


def test_sweep_reuses_universe_compile_per_unique_scope(tmp_path):
    class CountingUniverseCompiler(UniverseCompiler):
        def __init__(self):
            super().__init__()
            self.calls = 0

        def compile(self, config, panel, context):
            self.calls += 1
            return super().compile(config, panel, context)

    sweep = _configs(tmp_path)
    compiler = CountingUniverseCompiler()
    runner = ResearchParameterSweepRunner(
        engine=ResearchConfigEngine(universe_compiler=compiler)
    )
    result = runner.prepare_sweep(
        sweep_config_path=sweep,
        root=tmp_path,
        panel=_panel(),
        universe_context=UniverseContext(
            p2_060_excluded_tickers=frozenset(),
            p2_060_exclusion_sha256=P2_SHA,
            theme_root=tmp_path / "themes",
        ),
        signal_context=SignalContext(source_revision="fixture-v1"),
        base_policy=PortfolioPolicyConfig(
            position_fraction=0.10,
            max_positions=10,
        ),
    )

    assert len(result.runs) == 16
    assert compiler.calls == 2


def test_stream_sweep_preserves_declared_and_constraint_counts(tmp_path):
    sweep = _configs(tmp_path)
    runner = ResearchParameterSweepRunner()
    stream = runner.stream_sweep(
        sweep_config_path=sweep,
        root=tmp_path,
        panel=_panel(),
        universe_context=UniverseContext(
            p2_060_excluded_tickers=frozenset(),
            p2_060_exclusion_sha256=P2_SHA,
            theme_root=tmp_path / "themes",
        ),
        signal_context=SignalContext(source_revision="fixture-v1"),
        base_policy=PortfolioPolicyConfig(
            position_fraction=0.10,
            max_positions=10,
        ),
    )

    items = list(stream.runs)
    assert stream.declared_combinations == 16
    assert stream.skipped_by_constraints == 0
    assert len(items) == 16
    assert all(item.parameters for item in items)
