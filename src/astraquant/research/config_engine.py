from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from astraquant.data.market_coordinates import SignalPriceSemantics
from astraquant.execution.service import SignalDeclaration
from astraquant.portfolio.performance_reporting import TradeReport, build_trade_report
from astraquant.portfolio.policy import PortfolioPolicyConfig
from astraquant.portfolio.strategy_simulator import CanonicalStrategySimulator, StrategySimulationResult
from astraquant.research.candidates import candidates_from_signal_frame
from astraquant.research.config_io import (
    load_exit_config,
    load_run_config,
    load_signal_config,
    load_universe_config,
)
from astraquant.research.exit_engine import CompiledExitPlan, ExitCompiler
from astraquant.research.feature_cache import FeatureCache
from astraquant.research.signal_engine import (
    SignalCompiler,
    SignalContext,
    SignalEvaluator,
    SignalPlan,
)
from astraquant.research.strategy_config import (
    ExitConfig,
    SignalConfig,
    StrategyRunConfig,
    UniverseConfig,
)
from astraquant.research.universe_engine import (
    UniverseCompiler,
    UniverseContext,
    UniverseMask,
)


@dataclass(frozen=True)
class PreparedResearchRun:
    run_config: StrategyRunConfig
    universe_config: UniverseConfig
    signal_config: SignalConfig
    exit_config: ExitConfig
    universe_mask: UniverseMask
    signal_frame: pd.DataFrame
    candidates: pd.DataFrame
    signal_plan: SignalPlan
    exit_plan: CompiledExitPlan
    portfolio_policy: PortfolioPolicyConfig
    feature_cache_hits: int
    feature_cache_misses: int


@dataclass(frozen=True)
class ExecutedResearchRun:
    prepared: PreparedResearchRun
    simulation: StrategySimulationResult
    trade_report: TradeReport


class ResearchConfigEngine:
    """Compile config research, then optionally execute it on the canonical stack.

    Preparation owns only universe/signal/exit-policy research artifacts.
    Execution remains delegated to CanonicalStrategySimulator and the existing
    RAW execution, settlement, corporate-action, valuation, and FIFO layers.
    """

    def __init__(
        self,
        *,
        universe_compiler: UniverseCompiler | None = None,
        signal_compiler: SignalCompiler | None = None,
        exit_compiler: ExitCompiler | None = None,
        feature_cache: FeatureCache | None = None,
    ) -> None:
        self.universe_compiler = universe_compiler or UniverseCompiler()
        self.signal_compiler = signal_compiler or SignalCompiler()
        self.exit_compiler = exit_compiler or ExitCompiler()
        self.feature_cache = feature_cache or FeatureCache()
        self.signal_evaluator = SignalEvaluator(self.feature_cache)

    @staticmethod
    def _resolve(root: Path, configured: str) -> Path:
        candidate = (root / configured).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError as exc:
            raise ValueError(f"config path escapes research root: {configured}") from exc
        return candidate

    def prepare_from_configs(
        self,
        *,
        run_config: StrategyRunConfig,
        universe_config: UniverseConfig,
        signal_config: SignalConfig,
        exit_config: ExitConfig,
        panel: pd.DataFrame,
        universe_context: UniverseContext,
        signal_context: SignalContext,
        base_policy: PortfolioPolicyConfig,
    ) -> PreparedResearchRun:
        mask = self.universe_compiler.compile(
            universe_config,
            panel,
            universe_context,
        )
        signal_plan = self.signal_compiler.compile(signal_config)
        signal_frame = self.signal_evaluator.evaluate(
            signal_plan,
            panel,
            mask,
            signal_context,
        )
        exit_plan = self.exit_compiler.compile(exit_config)
        policy = exit_plan.apply_to_policy(base_policy)
        declaration = SignalDeclaration(
            source=f"CONFIG:{signal_config.name}",
            price_semantics=SignalPriceSemantics.SCALE_SENSITIVE,
        )
        candidates = candidates_from_signal_frame(
            signal_frame,
            declaration=declaration,
        )

        return PreparedResearchRun(
            run_config=run_config,
            universe_config=universe_config,
            signal_config=signal_config,
            exit_config=exit_config,
            universe_mask=mask,
            signal_frame=signal_frame,
            candidates=candidates,
            signal_plan=signal_plan,
            exit_plan=exit_plan,
            portfolio_policy=policy,
            feature_cache_hits=self.feature_cache.hits,
            feature_cache_misses=self.feature_cache.misses,
        )

    def prepare(
        self,
        *,
        run_config_path: str | Path,
        root: str | Path,
        panel: pd.DataFrame,
        universe_context: UniverseContext,
        signal_context: SignalContext,
        base_policy: PortfolioPolicyConfig,
    ) -> PreparedResearchRun:
        root_path = Path(root).resolve()
        run_cfg = load_run_config(run_config_path)
        universe_cfg = load_universe_config(self._resolve(root_path, run_cfg.universe))
        signal_cfg = load_signal_config(self._resolve(root_path, run_cfg.signal))
        exit_cfg = load_exit_config(self._resolve(root_path, run_cfg.exit))
        return self.prepare_from_configs(
            run_config=run_cfg,
            universe_config=universe_cfg,
            signal_config=signal_cfg,
            exit_config=exit_cfg,
            panel=panel,
            universe_context=universe_context,
            signal_context=signal_context,
            base_policy=base_policy,
        )


    def simulate_prepared(
        self,
        *,
        prepared: PreparedResearchRun,
        simulator: CanonicalStrategySimulator,
        sessions,
        corporate_actions=None,
    ) -> StrategySimulationResult:
        """Run prepared config candidates through the unchanged canonical simulator."""
        return simulator.run(
            sessions=list(sessions),
            candidates=prepared.candidates,
            corporate_actions=corporate_actions,
        )


    def execute_prepared(
        self,
        *,
        prepared: PreparedResearchRun,
        simulator: CanonicalStrategySimulator,
        sessions,
        corporate_actions=None,
    ) -> ExecutedResearchRun:
        """Execute config candidates and attach CA-aware FIFO trade statistics."""
        simulation = self.simulate_prepared(
            prepared=prepared,
            simulator=simulator,
            sessions=sessions,
            corporate_actions=corporate_actions,
        )
        return ExecutedResearchRun(
            prepared=prepared,
            simulation=simulation,
            trade_report=build_trade_report(simulator.portfolio),
        )
