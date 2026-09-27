from datetime import date

import pytest

from astraquant.validation.walk_forward import (
    LockedOOS,
    TimeWindow,
    WalkForwardFold,
    assert_locked_oos_untouched,
    validate_fold_sequence,
)


def test_fold_requires_strict_temporal_ordering():
    fold = WalkForwardFold(
        fold_id="F1",
        train=TimeWindow(date(2020, 1, 1), date(2021, 12, 31)),
        validation=TimeWindow(date(2022, 1, 1), date(2022, 6, 30)),
        test=TimeWindow(date(2022, 7, 1), date(2022, 12, 31)),
    )
    validate_fold_sequence([fold])


def test_locked_oos_overlap_is_rejected():
    locked = LockedOOS(TimeWindow(date(2025, 1, 1), date(2025, 12, 31)))
    with pytest.raises(ValueError):
        assert_locked_oos_untouched(
            locked,
            [TimeWindow(date(2024, 6, 1), date(2025, 2, 1))],
        )


def test_locked_oos_non_overlap_passes():
    locked = LockedOOS(TimeWindow(date(2025, 1, 1), date(2025, 12, 31)))
    assert_locked_oos_untouched(
        locked,
        [TimeWindow(date(2023, 1, 1), date(2024, 12, 31))],
    )
