from __future__ import annotations

from dataclasses import dataclass


class PerformanceLockedError(RuntimeError):
    pass


@dataclass(frozen=True)
class AccountingReadiness:
    signal_source_declared: bool
    entry_raw: bool
    stop_observation_raw: bool
    exit_raw: bool
    sizing_raw: bool
    mark_raw: bool
    share_count_reconciles: bool
    cash_reconciles: bool
    receivables_reconcile: bool
    corporate_actions_reconcile: bool
    nav_reconciles: bool
    no_adjusted_execution_fallback: bool
    canonical_execution_path_active: bool
    normalized_ca_view_active: bool
    ca_payment_dates_settle: bool
    pit_unsafe_ca_excluded: bool
    terminal_security_lifecycle_active: bool
    long_horizon_canonical_probe_passed: bool

    @property
    def passed(self) -> bool:
        return all(self.__dict__.values())

    @property
    def failed_checks(self) -> tuple[str, ...]:
        return tuple(name for name, ok in self.__dict__.items() if not ok)

    def require_performance_unlocked(self) -> None:
        if not self.passed:
            failed = ", ".join(self.failed_checks)
            raise PerformanceLockedError(
                f"performance metrics remain locked; failed accounting gates: {failed}"
            )
