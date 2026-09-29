from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from pathlib import Path

import pandas as pd

from astraquant.portfolio.policy import PortfolioPolicyConfig
from astraquant.research.config_engine import PreparedResearchRun, ResearchConfigEngine
from astraquant.research.config_io import (
    load_batch_matrix_config,
    load_exit_config,
    load_signal_config,
    load_universe_config,
)
from astraquant.research.signal_engine import SignalContext
from astraquant.research.strategy_config import StrategyRunConfig
from astraquant.research.universe_engine import UniverseContext


@dataclass(frozen=True)
class BatchPreparationResult:
    matrix_name: str
    runs: tuple[PreparedResearchRun, ...]
    summary: pd.DataFrame
    feature_cache_hits: int
    feature_cache_misses: int


class ResearchBatchRunner:
    def __init__(self, engine: ResearchConfigEngine | None = None) -> None:
        self.engine = engine or ResearchConfigEngine()

    def prepare_matrix(
        self,
        *,
        matrix_config_path: str | Path,
        root: str | Path,
        panel: pd.DataFrame,
        universe_context: UniverseContext,
        signal_context: SignalContext,
        base_policy: PortfolioPolicyConfig,
    ) -> BatchPreparationResult:
        root_path = Path(root).resolve()
        matrix = load_batch_matrix_config(matrix_config_path)

        universes = {
            path: load_universe_config(self.engine._resolve(root_path, path))
            for path in matrix.universes
        }
        signals = {
            path: load_signal_config(self.engine._resolve(root_path, path))
            for path in matrix.signals
        }
        exits = {
            path: load_exit_config(self.engine._resolve(root_path, path))
            for path in matrix.exits
        }

        prepared: list[PreparedResearchRun] = []
        rows: list[dict[str, object]] = []
        seen_names: set[str] = set()

        for universe_path, signal_path, exit_path in product(
            matrix.universes,
            matrix.signals,
            matrix.exits,
        ):
            ucfg = universes[universe_path]
            scfg = signals[signal_path]
            ecfg = exits[exit_path]
            run_name = f"{matrix.name}__{ucfg.name}__{scfg.name}__{ecfg.name}"
            if run_name in seen_names:
                raise ValueError(f"duplicate expanded batch run name: {run_name}")
            seen_names.add(run_name)

            run_cfg = StrategyRunConfig(
                run_name=run_name,
                strategy_version=run_name,
                universe=universe_path,
                signal=signal_path,
                exit=exit_path,
                execution_assumptions_id=matrix.execution_assumptions_id,
            )
            result = self.engine.prepare_from_configs(
                run_config=run_cfg,
                universe_config=ucfg,
                signal_config=scfg,
                exit_config=ecfg,
                panel=panel,
                universe_context=universe_context,
                signal_context=signal_context,
                base_policy=base_policy,
            )
            prepared.append(result)
            rows.append(
                {
                    "run_name": run_name,
                    "universe": ucfg.name,
                    "signal": scfg.name,
                    "exit": ecfg.name,
                    "universe_rows_counting": int(
                        result.universe_mask.frame["counts"].sum()
                    ),
                    "signal_candidates": int(
                        result.signal_frame["counts_as_candidate"].sum()
                    ),
                    "feature_cache_hits": result.feature_cache_hits,
                    "feature_cache_misses": result.feature_cache_misses,
                }
            )

        return BatchPreparationResult(
            matrix_name=matrix.name,
            runs=tuple(prepared),
            summary=pd.DataFrame(rows),
            feature_cache_hits=self.engine.feature_cache.hits,
            feature_cache_misses=self.engine.feature_cache.misses,
        )
