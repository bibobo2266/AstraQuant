from pathlib import Path

import pandas as pd
import pytest

from astraquant.portfolio.policy import (
    CapacitySelectionRule,
    PortfolioPolicyConfig,
)
from astraquant.research.component_registry import UnsupportedComponentError
from astraquant.research.config_engine import ResearchConfigEngine
from astraquant.research.feature_cache import FeatureCache
from astraquant.research.signal_engine import SignalCompiler, SignalContext
from astraquant.research.strategy_config import ComponentSpec, SignalConfig
from astraquant.research.universe_engine import UniverseContext


P2_SHA = "379d58f6a8aa06b1e020d56911930f4bc01861d3eeca109613d9e5b1e490d134"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _panel() -> pd.DataFrame:
    rows = []
    prices = [10.0, 11.0, 12.0, 11.0, 13.0, 14.0]
    for i, px in enumerate(prices):
        rows.append(
            {
                "date": pd.Timestamp("2026-01-02") + pd.Timedelta(days=i),
                "stock_id": "2330",
                "close": px,
                "Trading_money": 1_000_000.0,
                "observed_trade": i != 3,
                "valid_ohlc": True,
            }
        )
    return pd.DataFrame(rows)


def _configs(root: Path) -> Path:
    _write(
        root / "configs/universes/u.yaml",
        f"""
schema_version: "1"
name: all
base:
  ticker_pattern: '^[1-9]\\d{{3}}$'
  min_close_twd: 10
  require_observed_trade: true
  require_valid_ohlc: true
  p2_060_exclusion_sha256: "{P2_SHA}"
combine: AND
pools:
  - type: ALL
    turnover_top_fraction: 1.0
""",
    )
    _write(
        root / "configs/signals/s.yaml",
        """
schema_version: "1"
name: high3
trigger:
  type: N_SESSION_HIGH
  params: {lookback: 3}
filters: []
ranking: []
""",
    )
    _write(
        root / "configs/exits/e.yaml",
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
    run = root / "configs/runs/r.yaml"
    _write(
        run,
        """
schema_version: "1"
run_name: executable_slice
universe: configs/universes/u.yaml
signal: configs/signals/s.yaml
exit: configs/exits/e.yaml
execution_assumptions_id: zero-cost
report_trade_stats_first: true
""",
    )
    return run


def test_config_engine_prepares_existing_canonical_slice_without_new_script(tmp_path):
    run = _configs(tmp_path)
    engine = ResearchConfigEngine(feature_cache=FeatureCache())
    base_policy = PortfolioPolicyConfig(
        position_fraction=0.10,
        max_positions=10,
        stop_fraction=0.20,
        max_hold_sessions=20,
        capacity_selection_rule=CapacitySelectionRule.TICKER_ASC,
    )

    prepared = engine.prepare(
        run_config_path=run,
        root=tmp_path,
        panel=_panel(),
        universe_context=UniverseContext(
            p2_060_excluded_tickers=frozenset(),
            p2_060_exclusion_sha256=P2_SHA,
        ),
        signal_context=SignalContext(source_revision="fixture-v1"),
        base_policy=base_policy,
    )

    assert len(prepared.universe_mask.frame) == len(_panel())
    assert len(prepared.signal_frame) == len(_panel())
    assert prepared.portfolio_policy.stop_fraction == 0.12
    assert prepared.portfolio_policy.max_hold_sessions == 250

    # The masked day remains in the series and still contributes to the rolling history.
    masked = prepared.universe_mask.frame
    assert not bool(
        masked.loc[masked["date"].eq(pd.Timestamp("2026-01-05")), "counts"].iloc[0]
    )

    candidates = prepared.signal_frame[
        prepared.signal_frame["counts_as_candidate"]
    ]
    assert list(candidates["signal_date"]) == [pd.Timestamp("2026-01-06")]
    assert list(prepared.candidates["stock_id"]) == ["2330"]
    assert prepared.candidates.iloc[0]["signal_source"] == "CONFIG:high3"
    assert prepared.candidates.iloc[0]["signal_price_semantics"] == "SCALE_SENSITIVE"
    assert prepared.candidates.iloc[0]["available_at"] > pd.Timestamp("2026-01-06")


def test_feature_cache_is_shared_across_config_runs(tmp_path):
    run = _configs(tmp_path)
    cache = FeatureCache()
    engine = ResearchConfigEngine(feature_cache=cache)
    kwargs = dict(
        run_config_path=run,
        root=tmp_path,
        panel=_panel(),
        universe_context=UniverseContext(
            p2_060_excluded_tickers=frozenset(),
            p2_060_exclusion_sha256=P2_SHA,
        ),
        signal_context=SignalContext(source_revision="fixture-v1"),
        base_policy=PortfolioPolicyConfig(
            position_fraction=0.10,
            max_positions=10,
        ),
    )
    engine.prepare(**kwargs)
    first_misses = cache.misses
    engine.prepare(**kwargs)

    assert first_misses == 1
    assert cache.misses == 1
    assert cache.hits >= 1


def test_unimplemented_signal_component_fails_at_compile_time():
    compiler = SignalCompiler()
    cfg = SignalConfig(
        name="not_ready",
        trigger=ComponentSpec(type="N_SESSION_HIGH", params={"lookback": 20}),
        filters=(ComponentSpec(type="ICHIMOKU", params={"mode": "CLOUD_BREAK"}),),
    )

    with pytest.raises(UnsupportedComponentError, match="ICHIMOKU"):
        compiler.compile(cfg)


def test_config_engine_simulate_prepared_passes_canonical_candidates(tmp_path):
    run = _configs(tmp_path)
    engine = ResearchConfigEngine()
    prepared = engine.prepare(
        run_config_path=run,
        root=tmp_path,
        panel=_panel(),
        universe_context=UniverseContext(
            p2_060_excluded_tickers=frozenset(),
            p2_060_exclusion_sha256=P2_SHA,
        ),
        signal_context=SignalContext(source_revision="fixture-v1"),
        base_policy=PortfolioPolicyConfig(position_fraction=0.10, max_positions=10),
    )

    class StubSimulator:
        def __init__(self):
            self.received = None

        def run(self, **kwargs):
            self.received = kwargs
            return "ok"

    simulator = StubSimulator()
    out = engine.simulate_prepared(
        prepared=prepared,
        simulator=simulator,
        sessions=[pd.Timestamp("2026-01-06").date(), pd.Timestamp("2026-01-07").date()],
    )
    assert out == "ok"
    assert simulator.received["signals"] is None if "signals" in simulator.received else True
    assert list(simulator.received["candidates"]["stock_id"]) == ["2330"]
