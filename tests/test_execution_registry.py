import pytest

from astraquant.execution.assumptions import ExecutionAssumptions
from astraquant.execution.registry import (
    ExecutionAssumptionRegistry,
    VersionedExecutionAssumptions,
)


def test_execution_assumption_versions_are_immutable_keys():
    registry = ExecutionAssumptionRegistry()
    item = VersionedExecutionAssumptions(
        assumptions_id="tw-daily",
        version="v1",
        assumptions=ExecutionAssumptions(
            price_source="next_open",
            timing_rule="signal close -> next session order",
        ),
    )
    registry.register(item)
    with pytest.raises(ValueError):
        registry.register(item)
