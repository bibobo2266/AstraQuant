from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Iterable

import pandas as pd

from astraquant.portfolio.policy import PortfolioPolicyConfig
from astraquant.research.exit_engine import CompiledExitPlan
from astraquant.research.feature_panel_integration import (
    FeaturePanelEligibilityEvidence,
    FeaturePanelIntegrationError,
    dataframe_sha256,
    stable_object_sha256,
    validate_feature_panel_evidence_files,
)
from astraquant.research.strategy_config import (
    ExitConfig,
    SignalConfig,
    StrategyRunConfig,
    UniverseConfig,
)
from astraquant.research.universe_engine import UniverseMask


def normalize_execution_sessions(
    sessions: Iterable[date | pd.Timestamp],
    *,
    feature_evidence: FeaturePanelEligibilityEvidence,
) -> tuple[str, ...]:
    """Normalize one explicit executable calendar.

    The hydration panel may include warmup dates that are not executable
    sessions. We therefore bind the caller-declared execution calendar as a
    separate ordered sequence, while requiring only that its closed range is
    covered by the validated hydrated panel/manifest range.
    """
    normalized: list[date] = []
    for raw in sessions:
        try:
            ts = pd.Timestamp(raw)
        except Exception as exc:
            raise FeaturePanelIntegrationError(
                f"invalid execution session: {raw!r}"
            ) from exc
        if pd.isna(ts):
            raise FeaturePanelIntegrationError(
                "execution sessions contain null/invalid dates"
            )
        normalized.append(ts.normalize().date())

    if not normalized:
        raise FeaturePanelIntegrationError(
            "execution sessions must not be empty"
        )
    for previous, current in zip(normalized, normalized[1:]):
        if current <= previous:
            raise FeaturePanelIntegrationError(
                "execution sessions must be strictly increasing and unique"
            )

    panel_start = date.fromisoformat(feature_evidence.panel_date_start)
    panel_end = date.fromisoformat(feature_evidence.panel_date_end)
    manifest_start = date.fromisoformat(
        feature_evidence.manifest_period_start
    )
    manifest_end = date.fromisoformat(feature_evidence.manifest_period_end)
    first = normalized[0]
    last = normalized[-1]
    if first < panel_start or last > panel_end:
        raise FeaturePanelIntegrationError(
            "execution sessions exceed hydrated panel evidence range"
        )
    if first < manifest_start or last > manifest_end:
        raise FeaturePanelIntegrationError(
            "execution sessions exceed manifest evidence range"
        )
    return tuple(item.isoformat() for item in normalized)


@dataclass(frozen=True)
class PreparedRunEligibilityEvidence:
    """Integrity binding from verified hydration inputs to one prepared run.

    This is an in-process integrity/provenance contract, not a cryptographic
    authorization token and not a malicious-tamper security system.
    """

    schema_version: str
    feature_evidence: FeaturePanelEligibilityEvidence
    signal_source_revision: str
    signal_availability_policy: str
    prepared_config_sha256: str
    compiled_exit_plan_sha256: str
    portfolio_policy_sha256: str
    hydrated_panel_sha256: str
    universe_mask_sha256: str
    signal_frame_sha256: str
    candidates_sha256: str
    execution_sessions: tuple[str, ...] | None
    execution_sessions_sha256: str | None
    execution_date_start: str | None
    execution_date_end: str | None
    evidence_sha256: str

    def payload_without_digest(self) -> dict[str, object]:
        payload = asdict(self)
        payload.pop("evidence_sha256", None)
        return payload

    def verify_self_digest(self) -> None:
        actual = stable_object_sha256(self.payload_without_digest())
        if actual != self.evidence_sha256:
            raise FeaturePanelIntegrationError(
                "prepared-run eligibility evidence digest mismatch"
            )


def _prepared_config_payload(
    *,
    run_config: StrategyRunConfig,
    universe_config: UniverseConfig,
    signal_config: SignalConfig,
    exit_config: ExitConfig,
    portfolio_policy: PortfolioPolicyConfig,
    signal_source_revision: str,
    signal_availability_policy: str,
) -> dict[str, object]:
    return {
        "run_config": run_config,
        "universe_config": universe_config,
        "signal_config": signal_config,
        "exit_config": exit_config,
        "portfolio_policy": portfolio_policy,
        "signal_source_revision": str(signal_source_revision),
        "signal_availability_policy": str(signal_availability_policy),
    }


def build_prepared_run_eligibility_evidence(
    *,
    feature_evidence: FeaturePanelEligibilityEvidence,
    hydrated_panel: pd.DataFrame,
    run_config: StrategyRunConfig,
    universe_config: UniverseConfig,
    signal_config: SignalConfig,
    exit_config: ExitConfig,
    exit_plan: CompiledExitPlan,
    portfolio_policy: PortfolioPolicyConfig,
    universe_mask: UniverseMask,
    signal_frame: pd.DataFrame,
    candidates: pd.DataFrame,
    signal_source_revision: str,
    signal_availability_policy: str,
    execution_sessions: Iterable[date | pd.Timestamp] | None = None,
) -> PreparedRunEligibilityEvidence:
    feature_evidence.verify_self_digest()
    validate_feature_panel_evidence_files(feature_evidence)

    panel_digest = dataframe_sha256(hydrated_panel)
    if panel_digest != feature_evidence.hydrated_panel_sha256:
        raise FeaturePanelIntegrationError(
            "prepared run hydrated panel does not match feature eligibility evidence"
        )

    config_digest = stable_object_sha256(
        _prepared_config_payload(
            run_config=run_config,
            universe_config=universe_config,
            signal_config=signal_config,
            exit_config=exit_config,
            portfolio_policy=portfolio_policy,
            signal_source_revision=signal_source_revision,
            signal_availability_policy=signal_availability_policy,
        )
    )
    normalized_sessions = (
        None
        if execution_sessions is None
        else normalize_execution_sessions(
            execution_sessions,
            feature_evidence=feature_evidence,
        )
    )
    base_payload = {
        "schema_version": "2",
        "feature_evidence": feature_evidence,
        "signal_source_revision": str(signal_source_revision),
        "signal_availability_policy": str(signal_availability_policy),
        "prepared_config_sha256": config_digest,
        "compiled_exit_plan_sha256": stable_object_sha256(exit_plan),
        "portfolio_policy_sha256": stable_object_sha256(portfolio_policy),
        "hydrated_panel_sha256": panel_digest,
        "universe_mask_sha256": dataframe_sha256(universe_mask.frame),
        "signal_frame_sha256": dataframe_sha256(signal_frame),
        "candidates_sha256": dataframe_sha256(candidates),
        "execution_sessions": normalized_sessions,
        "execution_sessions_sha256": (
            None
            if normalized_sessions is None
            else stable_object_sha256(normalized_sessions)
        ),
        "execution_date_start": (
            None if normalized_sessions is None else normalized_sessions[0]
        ),
        "execution_date_end": (
            None if normalized_sessions is None else normalized_sessions[-1]
        ),
    }
    return PreparedRunEligibilityEvidence(
        **base_payload,
        evidence_sha256=stable_object_sha256(base_payload),
    )


def validate_prepared_run_eligibility_evidence(
    *,
    evidence: PreparedRunEligibilityEvidence,
    run_config: StrategyRunConfig,
    universe_config: UniverseConfig,
    signal_config: SignalConfig,
    exit_config: ExitConfig,
    exit_plan: CompiledExitPlan,
    portfolio_policy: PortfolioPolicyConfig,
    universe_mask: UniverseMask,
    signal_frame: pd.DataFrame,
    candidates: pd.DataFrame,
    signal_source_revision: str,
    signal_availability_policy: str,
) -> None:
    evidence.verify_self_digest()
    validate_feature_panel_evidence_files(evidence.feature_evidence)

    expected_config_digest = stable_object_sha256(
        _prepared_config_payload(
            run_config=run_config,
            universe_config=universe_config,
            signal_config=signal_config,
            exit_config=exit_config,
            portfolio_policy=portfolio_policy,
            signal_source_revision=signal_source_revision,
            signal_availability_policy=signal_availability_policy,
        )
    )
    checks = {
        "prepared config": (
            expected_config_digest,
            evidence.prepared_config_sha256,
        ),
        "compiled exit plan": (
            stable_object_sha256(exit_plan),
            evidence.compiled_exit_plan_sha256,
        ),
        "prepared portfolio policy": (
            stable_object_sha256(portfolio_policy),
            evidence.portfolio_policy_sha256,
        ),
        "universe mask": (
            dataframe_sha256(universe_mask.frame),
            evidence.universe_mask_sha256,
        ),
        "signal frame": (
            dataframe_sha256(signal_frame),
            evidence.signal_frame_sha256,
        ),
        "candidates": (
            dataframe_sha256(candidates),
            evidence.candidates_sha256,
        ),
    }
    for name, (actual, expected) in checks.items():
        if actual != expected:
            raise FeaturePanelIntegrationError(
                f"prepared-run eligibility {name} fingerprint mismatch"
            )

    if str(signal_source_revision) != evidence.signal_source_revision:
        raise FeaturePanelIntegrationError(
            "prepared-run signal source revision mismatch"
        )
    if str(signal_availability_policy) != evidence.signal_availability_policy:
        raise FeaturePanelIntegrationError(
            "prepared-run signal availability policy mismatch"
        )
    if (
        evidence.hydrated_panel_sha256
        != evidence.feature_evidence.hydrated_panel_sha256
    ):
        raise FeaturePanelIntegrationError(
            "prepared-run hydrated panel identity drift"
        )


def validate_prepared_execution_binding(
    *,
    evidence: PreparedRunEligibilityEvidence,
    exit_plan: CompiledExitPlan,
    actual_policy: PortfolioPolicyConfig,
    sessions: Iterable[date | pd.Timestamp],
    candidates: pd.DataFrame,
) -> None:
    """Validate actual simulator inputs against one prepared-run evidence object."""
    evidence.verify_self_digest()
    validate_feature_panel_evidence_files(evidence.feature_evidence)
    evidence.feature_evidence.require_strategy_verified()

    if evidence.execution_sessions is None:
        raise FeaturePanelIntegrationError(
            "prepared-run evidence has no execution-session contract"
        )
    normalized_sessions = normalize_execution_sessions(
        sessions,
        feature_evidence=evidence.feature_evidence,
    )
    if normalized_sessions != evidence.execution_sessions:
        raise FeaturePanelIntegrationError(
            "execution sessions do not match prepared-run evidence"
        )
    if (
        stable_object_sha256(normalized_sessions)
        != evidence.execution_sessions_sha256
    ):
        raise FeaturePanelIntegrationError(
            "execution-session fingerprint mismatch"
        )
    checks = {
        "compiled exit plan": (
            stable_object_sha256(exit_plan),
            evidence.compiled_exit_plan_sha256,
        ),
        "actual simulator policy": (
            stable_object_sha256(actual_policy),
            evidence.portfolio_policy_sha256,
        ),
        "actual candidates": (
            dataframe_sha256(candidates),
            evidence.candidates_sha256,
        ),
    }
    for name, (actual, expected) in checks.items():
        if actual != expected:
            raise FeaturePanelIntegrationError(
                f"execution binding {name} fingerprint mismatch"
            )
