import pandas as pd
import pytest

from astraquant.research.batch_screen import (
    FeatureTerm,
    ScreeningRecipe,
    batch_screen,
    equal_weight_combinations,
)


def _frame():
    rows = []
    for date in ["2024-01-02", "2025-01-02"]:
        for i in range(20):
            rows.append(
                {
                    "date": date,
                    "stock_id": str(1000 + i),
                    "momentum": float(i),
                    "quality": float(19 - abs(i - 15)),
                    "junk": float((i * 7) % 20),
                    "forward_return": (i - 10) / 100.0,
                }
            )
    return pd.DataFrame(rows)


def test_batch_screen_supports_stacked_features():
    recipes = (
        ScreeningRecipe(
            "momentum_only",
            (FeatureTerm("momentum"),),
            selection_fraction=0.20,
        ),
        ScreeningRecipe(
            "momentum_plus_quality",
            (FeatureTerm("momentum"), FeatureTerm("quality")),
            selection_fraction=0.20,
        ),
    )
    result = batch_screen(_frame(), recipes)

    assert set(result["recipe_id"]) == {
        "momentum_only",
        "momentum_plus_quality",
    }
    assert result["selected_dates"].eq(2).all()
    assert result["selected_rows"].eq(8).all()


def test_batch_screen_handles_inverse_terms():
    recipes = (
        ScreeningRecipe(
            "prefer_low_momentum",
            (FeatureTerm("momentum", direction=-1),),
            selection_fraction=0.10,
        ),
    )
    result = batch_screen(_frame(), recipes)
    assert result.iloc[0]["mean_forward_return"] < 0


def test_equal_weight_combinations_can_generate_large_recipe_sets():
    recipes = equal_weight_combinations(
        feature_names=[f"f{i}" for i in range(15)],
        sizes=[2],
    )
    assert len(recipes) == 105
    assert len({x.recipe_id for x in recipes}) == 105


def test_duplicate_recipe_terms_are_rejected():
    with pytest.raises(ValueError, match="unique"):
        ScreeningRecipe(
            "bad",
            (FeatureTerm("x"), FeatureTerm("x")),
        )
