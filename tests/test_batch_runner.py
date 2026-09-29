from pathlib import Path

import pandas as pd

from astraquant.portfolio.policy import PortfolioPolicyConfig
from astraquant.research.batch_runner import ResearchBatchRunner
from astraquant.research.signal_engine import SignalContext
from astraquant.research.universe_engine import UniverseContext


P2_SHA = "379d58f6a8aa06b1e020d56911930f4bc01861d3eeca109613d9e5b1e490d134"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _panel() -> pd.DataFrame:
    rows = []
    for ticker, offset in [("2330", 0.0), ("2317", 10.0), ("2454", 20.0), ("2308", 30.0)]:
        for i in range(8):
            rows.append(
                {
                    "date": pd.Timestamp("2026-01-02") + pd.Timedelta(days=i),
                    "stock_id": ticker,
                    "close": 100.0 + offset + i,
                    "Trading_money": 10_000_000.0 - offset * 1000,
                    "observed_trade": True,
                    "valid_ohlc": True,
                }
            )
    return pd.DataFrame(rows)


def _write_matrix(root: Path) -> Path:
    _write(
        root / "configs/universes/all.yaml",
        f"""
schema_version: "1"
name: all
base:
  ticker_pattern: '^[1-9]\\d{{3}}$'
  min_close_twd: 10
  require_observed_trade: true
  require_valid_ohlc: true
  p2_060_exclusion_sha256: "{P2_SHA}"
pools:
  - type: ALL
    turnover_top_fraction: 1.0
""",
    )
    for name in ["high3_a", "high3_b"]:
        _write(
            root / f"configs/signals/{name}.yaml",
            f"""
schema_version: "1"
name: {name}
trigger:
  type: N_SESSION_HIGH
  params: {{lookback: 3}}
filters: []
ranking: []
""",
        )
    _write(
        root / "configs/exits/stop.yaml",
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
    matrix = root / "configs/batches/matrix.yaml"
    _write(
        matrix,
        """
schema_version: "1"
name: shared_cache
universes:
  - configs/universes/all.yaml
signals:
  - configs/signals/high3_a.yaml
  - configs/signals/high3_b.yaml
exits:
  - configs/exits/stop.yaml
execution_assumptions_id: zero-cost
max_combinations: 10
report_trade_stats_first: true
""",
    )
    return matrix


def test_batch_matrix_expands_configs_and_reuses_feature_cache(tmp_path):
    matrix = _write_matrix(tmp_path)
    runner = ResearchBatchRunner()
    result = runner.prepare_matrix(
        matrix_config_path=matrix,
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

    assert len(result.runs) == 2
    assert len(result.summary) == 2
    assert result.feature_cache_misses == 1
    assert result.feature_cache_hits >= 1
    assert set(result.summary["signal"]) == {"high3_a", "high3_b"}


def test_batch_matrix_enforces_combination_cap(tmp_path):
    matrix = _write_matrix(tmp_path)
    text = matrix.read_text(encoding="utf-8").replace("max_combinations: 10", "max_combinations: 1")
    matrix.write_text(text, encoding="utf-8")

    runner = ResearchBatchRunner()
    try:
        runner.prepare_matrix(
            matrix_config_path=matrix,
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
    except Exception as exc:
        assert "exceeds max_combinations" in str(exc)
    else:
        raise AssertionError("matrix cap should reject oversized batch")
