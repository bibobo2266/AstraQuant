from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from astraquant.portfolio.policy import PortfolioPolicyConfig
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
    hydrated_panel_sha256: str
    universe_mask_sha256: str
    signal_frame_sha256: str
    candidates_sha256: str
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
    portfolio_policy: PortfolioPolicyConfig,
    universe_mask: UniverseMask,
    signal_frame: pd.DataFrame,
    candidates: pd.DataFrame,
    signal_source_revision: str,
    signal_availability_policy: str,
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
    base_payload = {
        "schema_version": "1",
        "feature_evidence": feature_evidence,
        "signal_source_revision": str(signal_source_revision),
        "signal_availability_policy": str(signal_availability_policy),
        "prepared_config_sha256": config_digest,
        "hydrated_panel_sha256": panel_digest,
        "universe_mask_sha256": dataframe_sha256(universe_mask.frame),
        "signal_frame_sha256": dataframe_sha256(signal_frame),
        "candidates_sha256": dataframe_sha256(candidates),
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
