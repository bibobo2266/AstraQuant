import pytest

from astraquant.validation.accounting_gate import (
    AccountingReadiness,
    PerformanceLockedError,
)


def _ready(**overrides):
    values = {
        "signal_source_declared": True,
        "entry_raw": True,
        "stop_observation_raw": True,
        "exit_raw": True,
        "sizing_raw": True,
        "mark_raw": True,
        "share_count_reconciles": True,
        "cash_reconciles": True,
        "receivables_reconcile": True,
        "corporate_actions_reconcile": True,
        "nav_reconciles": True,
        "no_adjusted_execution_fallback": True,
        "canonical_execution_path_active": True,
        "normalized_ca_view_active": True,
        "ca_payment_dates_settle": True,
        "pit_unsafe_ca_excluded": True,
        "terminal_security_lifecycle_active": True,
        "long_horizon_canonical_probe_passed": True,
    }
    values.update(overrides)
    return AccountingReadiness(**values)


def test_performance_unlock_requires_all_accounting_gates():
    gate = _ready()
    gate.require_performance_unlocked()
    assert gate.passed
    assert gate.failed_checks == ()


def test_legacy_or_noncanonical_execution_path_keeps_performance_locked():
    gate = _ready(canonical_execution_path_active=False)

    assert not gate.passed
    assert gate.failed_checks == ("canonical_execution_path_active",)
    with pytest.raises(PerformanceLockedError, match="canonical_execution_path_active"):
        gate.require_performance_unlocked()


def test_any_accounting_failure_keeps_performance_locked():
    gate = _ready(nav_reconciles=False, receivables_reconcile=False)

    assert not gate.passed
    assert set(gate.failed_checks) == {"nav_reconciles", "receivables_reconcile"}
    with pytest.raises(PerformanceLockedError):
        gate.require_performance_unlocked()


def test_long_horizon_or_source_quality_failure_keeps_performance_locked():
    gate = _ready(
        long_horizon_canonical_probe_passed=False,
        pit_unsafe_ca_excluded=False,
    )

    assert not gate.passed
    assert set(gate.failed_checks) == {
        "long_horizon_canonical_probe_passed",
        "pit_unsafe_ca_excluded",
    }
    with pytest.raises(PerformanceLockedError):
        gate.require_performance_unlocked()
