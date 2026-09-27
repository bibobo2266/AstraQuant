from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Sequence


@dataclass(frozen=True)
class TimeWindow:
    start: date
    end: date

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError("window end must be on or after start")


@dataclass(frozen=True)
class WalkForwardFold:
    fold_id: str
    train: TimeWindow
    validation: TimeWindow
    test: TimeWindow

    def __post_init__(self) -> None:
        if not (self.train.end < self.validation.start):
            raise ValueError("train must end before validation starts")
        if not (self.validation.end < self.test.start):
            raise ValueError("validation must end before test starts")


def validate_fold_sequence(folds: Sequence[WalkForwardFold]) -> None:
    """Validate temporal ordering without making assumptions about fold overlap.

    Overlap between adjacent folds is allowed because expanding/rolling
    walk-forward designs often reuse training history. Within each fold,
    train -> validation -> test ordering is strict.
    """
    seen: set[str] = set()
    previous_test_start: date | None = None

    for fold in folds:
        if fold.fold_id in seen:
            raise ValueError(f"duplicate fold id: {fold.fold_id}")
        seen.add(fold.fold_id)

        if previous_test_start is not None and fold.test.start <= previous_test_start:
            raise ValueError("test windows must advance forward in time")
        previous_test_start = fold.test.start


@dataclass(frozen=True)
class LockedOOS:
    window: TimeWindow
    label: str = "locked_future_oos"


def assert_locked_oos_untouched(
    locked: LockedOOS,
    used_windows: Sequence[TimeWindow],
) -> None:
    """Reject any selection/tuning window that overlaps locked future OOS."""
    for window in used_windows:
        overlaps = not (window.end < locked.window.start or window.start > locked.window.end)
        if overlaps:
            raise ValueError(
                f"window {window.start}..{window.end} overlaps {locked.label} "
                f"{locked.window.start}..{locked.window.end}"
            )
