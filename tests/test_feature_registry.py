import pytest

from astraquant.features.registry import FeatureDefinition, FeatureRegistry


def test_feature_versions_are_immutable_registry_keys():
    registry = FeatureRegistry()
    feature = FeatureDefinition(
        name="rs_120",
        version="v1",
        family="relative_strength",
        description="120-session relative strength feature",
        point_in_time_safe=True,
        availability_rule="close available after session close",
    )
    registry.register(feature)
    with pytest.raises(ValueError):
        registry.register(feature)


def test_registry_retrieves_exact_version():
    registry = FeatureRegistry()
    feature = FeatureDefinition(
        name="persistence",
        version="v1",
        family="persistence",
        description="Path-quality feature",
        point_in_time_safe=True,
    )
    registry.register(feature)
    assert registry.get("persistence", "v1") == feature
