import pytest

from astraquant.data.market_coordinates import SignalPriceSemantics
from astraquant.features.registry import CAWindowRequirement, FeatureDefinition, FeatureRegistry


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


def test_feature_registry_preserves_price_and_ca_semantics():
    registry = FeatureRegistry()
    feature = FeatureDefinition(
        name="breakout_250",
        version="v1",
        family="technical",
        description="250-session adjusted-price breakout",
        point_in_time_safe=True,
        availability_rule="signal known after session close",
        price_semantics=SignalPriceSemantics.SCALE_SENSITIVE,
        ca_window_requirement=CAWindowRequirement.CONSISTENT_ADJUSTMENT_WITHIN_LOOKBACK,
    )

    registry.register(feature)
    stored = registry.get("breakout_250", "v1")

    assert stored.price_semantics is SignalPriceSemantics.SCALE_SENSITIVE
    assert (
        stored.ca_window_requirement
        is CAWindowRequirement.CONSISTENT_ADJUSTMENT_WITHIN_LOOKBACK
    )
