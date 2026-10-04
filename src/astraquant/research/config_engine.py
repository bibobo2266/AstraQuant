from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import pandas as pd

from astraquant.data.market_coordinates import SignalPriceSemantics
from astraquant.execution.service import SignalDeclaration
from astraquant.portfolio.performance_reporting import TradeReport, build_trade_report
from astraquant.portfolio.policy import PortfolioPolicyConfig
from astraquant.portfolio.strategy_simulator import CanonicalStrategySimulator, StrategySimulationResult
from astraquant.research.baseline_60d_simulation import (
    BaselineSimulationContext,
    BaselineSimulationMode,
)
from astraquant.research.candidates import candidates_from_signal_frame
from astraquant.research.config_io import (
    load_exit_config,
    load_run_config,
    load_signal_config,
    load_universe_config,
)
from astraquant.research.exit_engine import CompiledExitPlan, ExitCompiler
from astraquant.research.feature_cache import FeatureCache
from astraquant.research.feature_panel_integration import (
    EligibilityEvidenceScope,
    FeaturePanelIntegrationError,
    FeaturePanelIntegrator,
    FeaturePanelJoinResult,
)
from astraquant.research.prepared_run_evidence import (
    PreparedRunEligibilityEvidence,
    build_prepared_run_eligibility_evidence,
    validate_prepared_run_eligibility_evidence,
)
from astraquant.research.rsi_computability import SignalComputabilityContext
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
    signal_source_revision: str = ""
    signal_availability_policy: str = "adjusted-research-close"
    eligibility_evidence: PreparedRunEligibilityEvidence | None = None


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

    @staticmethod
    def _candidate_mask_column(
        *,
        signal_plan: SignalPlan,
        signal_computability_context: SignalComputabilityContext | None,
    ) -> str:
        if signal_computability_context is None:
            return "counts_as_candidate"
        if signal_plan.config.ranking:
            raise ValueError(
                "strict RSI computability is enabled, but configured ranking "
                "has no canonical downstream ordering/capacity contract; "
                "refusing to fall back to legacy ranking values"
            )
        return "strict_counts_as_candidate"

    def build_candidates(
        self,
        *,
        signal_frame: pd.DataFrame,
        signal_plan: SignalPlan,
        signal_computability_context: SignalComputabilityContext | None,
    ) -> pd.DataFrame:
        declaration = SignalDeclaration(
            source=f"CONFIG:{signal_plan.config.name}",
            price_semantics=SignalPriceSemantics.SCALE_SENSITIVE,
        )
        return candidates_from_signal_frame(
            signal_frame,
            declaration=declaration,
            candidate_mask_column=self._candidate_mask_column(
                signal_plan=signal_plan,
                signal_computability_context=signal_computability_context,
            ),
        )

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
        signal_computability_context: SignalComputabilityContext | None = None,
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
            computability_context=signal_computability_context,
        )
        exit_plan = self.exit_compiler.compile(exit_config)
        policy = exit_plan.apply_to_policy(base_policy)
        candidates = self.build_candidates(
            signal_frame=signal_frame,
            signal_plan=signal_plan,
            signal_computability_context=signal_computability_context,
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
            signal_source_revision=str(signal_context.source_revision),
            signal_availability_policy=str(signal_context.availability_policy),
        )

    def prepare_from_hydrated_configs(
        self,
        *,
        run_config: StrategyRunConfig,
        universe_config: UniverseConfig,
        signal_config: SignalConfig,
        exit_config: ExitConfig,
        feature_integrator: FeaturePanelIntegrator,
        feature_join_result: FeaturePanelJoinResult,
        universe_context: UniverseContext,
        signal_context: SignalContext,
        base_policy: PortfolioPolicyConfig,
        signal_computability_context: SignalComputabilityContext | None = None,
    ) -> PreparedResearchRun:
        """Prepare one run from an already-validated hydration result.

        The join result is revalidated against the current manifest/artifact
        bytes and current hydrated frame before any research compilation.
        """
        feature_integrator.validate_join_result(feature_join_result)
        prepared = self.prepare_from_configs(
            run_config=run_config,
            universe_config=universe_config,
            signal_config=signal_config,
            exit_config=exit_config,
            panel=feature_join_result.frame,
            universe_context=universe_context,
            signal_context=signal_context,
            base_policy=base_policy,
            signal_computability_context=signal_computability_context,
        )
        evidence = build_prepared_run_eligibility_evidence(
            feature_evidence=feature_join_result.evidence,
            hydrated_panel=feature_join_result.frame,
            run_config=prepared.run_config,
            universe_config=prepared.universe_config,
            signal_config=prepared.signal_config,
            exit_config=prepared.exit_config,
            portfolio_policy=prepared.portfolio_policy,
            universe_mask=prepared.universe_mask,
            signal_frame=prepared.signal_frame,
            candidates=prepared.candidates,
            signal_source_revision=prepared.signal_source_revision,
            signal_availability_policy=prepared.signal_availability_policy,
        )
        return replace(prepared, eligibility_evidence=evidence)

    def prepare_hydrated(
        self,
        *,
        run_config_path: str | Path,
        root: str | Path,
        feature_integrator: FeaturePanelIntegrator,
        feature_join_result: FeaturePanelJoinResult,
        universe_context: UniverseContext,
        signal_context: SignalContext,
        base_policy: PortfolioPolicyConfig,
        signal_computability_context: SignalComputabilityContext | None = None,
    ) -> PreparedResearchRun:
        root_path = Path(root).resolve()
        run_cfg = load_run_config(run_config_path)
        universe_cfg = load_universe_config(
            self._resolve(root_path, run_cfg.universe)
        )
        signal_cfg = load_signal_config(
            self._resolve(root_path, run_cfg.signal)
        )
        exit_cfg = load_exit_config(
            self._resolve(root_path, run_cfg.exit)
        )
        return self.prepare_from_hydrated_configs(
            run_config=run_cfg,
            universe_config=universe_cfg,
            signal_config=signal_cfg,
            exit_config=exit_cfg,
            feature_integrator=feature_integrator,
            feature_join_result=feature_join_result,
            universe_context=universe_context,
            signal_context=signal_context,
            base_policy=base_policy,
            signal_computability_context=signal_computability_context,
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
        signal_computability_context: SignalComputabilityContext | None = None,
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
            signal_computability_context=signal_computability_context,
        )


    def validate_prepared_eligibility(
        self,
        prepared: PreparedResearchRun,
    ) -> None:
        evidence = prepared.eligibility_evidence
        if evidence is None:
            raise FeaturePanelIntegrationError(
                "PreparedResearchRun has no eligibility evidence"
            )
        validate_prepared_run_eligibility_evidence(
            evidence=evidence,
            run_config=prepared.run_config,
            universe_config=prepared.universe_config,
            signal_config=prepared.signal_config,
            exit_config=prepared.exit_config,
            portfolio_policy=prepared.portfolio_policy,
            universe_mask=prepared.universe_mask,
            signal_frame=prepared.signal_frame,
            candidates=prepared.candidates,
            signal_source_revision=prepared.signal_source_revision,
            signal_availability_policy=prepared.signal_availability_policy,
        )

    def simulate_prepared(
        self,
        *,
        prepared: PreparedResearchRun,
        simulator: CanonicalStrategySimulator,
        sessions,
        corporate_actions=None,
        baseline_context: BaselineSimulationContext | None = None,
    ) -> StrategySimulationResult:
        """Run prepared candidates through the canonical simulator.

        The compiled exit plan is always passed through. Baseline close rules
        remain inert unless the exact compiled baseline pair and an explicit
        baseline_context are both present.
        """
        if prepared.exit_plan.baseline_60d_enabled and baseline_context is not None:
            # Formal mode stops here before any evidence/artifact read.
            baseline_context.require_runnable()
            self.validate_prepared_eligibility(prepared)
            evidence = prepared.eligibility_evidence
            assert evidence is not None
            if baseline_context.mode is BaselineSimulationMode.SYNTHETIC_FIXTURE:
                if (
                    evidence.feature_evidence.scope
                    is not EligibilityEvidenceScope.SYNTHETIC_FIXTURE
                ):
                    raise FeaturePanelIntegrationError(
                        "synthetic baseline simulation requires "
                        "SYNTHETIC_FIXTURE eligibility evidence"
                    )
                evidence.feature_evidence.require_strategy_verified()
        return simulator.run(
            sessions=list(sessions),
            candidates=prepared.candidates,
            corporate_actions=corporate_actions,
            exit_plan=prepared.exit_plan,
            baseline_context=baseline_context,
        )


    def execute_prepared(
        self,
        *,
        prepared: PreparedResearchRun,
        simulator: CanonicalStrategySimulator,
        sessions,
        corporate_actions=None,
        baseline_context: BaselineSimulationContext | None = None,
    ) -> ExecutedResearchRun:
        """Execute config candidates and attach CA-aware FIFO trade statistics."""
        simulation = self.simulate_prepared(
            prepared=prepared,
            simulator=simulator,
            sessions=sessions,
            corporate_actions=corporate_actions,
            baseline_context=baseline_context,
        )
        return ExecutedResearchRun(
            prepared=prepared,
            simulation=simulation,
            trade_report=build_trade_report(simulator.portfolio),
        )
