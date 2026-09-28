from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from math import ceil
from typing import Iterable

import pandas as pd


@dataclass(frozen=True)
class FeatureTerm:
    feature: str
    direction: int = 1
    weight: float = 1.0

    def __post_init__(self) -> None:
        if not self.feature:
            raise ValueError("feature must be non-empty")
        if self.direction not in {-1, 1}:
            raise ValueError("direction must be -1 or 1")
        if self.weight <= 0:
            raise ValueError("weight must be positive")


@dataclass(frozen=True)
class ScreeningRecipe:
    recipe_id: str
    terms: tuple[FeatureTerm, ...]
    selection_fraction: float = 0.10

    def __post_init__(self) -> None:
        if not self.recipe_id:
            raise ValueError("recipe_id must be non-empty")
        if not self.terms:
            raise ValueError("recipe must contain at least one feature term")
        names = [term.feature for term in self.terms]
        if len(names) != len(set(names)):
            raise ValueError("recipe feature terms must be unique")
        if not 0 < self.selection_fraction <= 1:
            raise ValueError("selection_fraction must be in (0, 1]")


def equal_weight_combinations(
    *,
    feature_names: Iterable[str],
    sizes: Iterable[int],
    selection_fraction: float = 0.10,
    prefix: str = "combo",
) -> tuple[ScreeningRecipe, ...]:
    names = tuple(dict.fromkeys(str(x) for x in feature_names))
    recipes: list[ScreeningRecipe] = []
    for size in sizes:
        if size <= 0:
            raise ValueError("combination size must be positive")
        for combo in combinations(names, size):
            recipe_id = prefix + "__" + "__".join(combo)
            recipes.append(
                ScreeningRecipe(
                    recipe_id=recipe_id,
                    terms=tuple(FeatureTerm(feature=x) for x in combo),
                    selection_fraction=selection_fraction,
                )
            )
    return tuple(recipes)


def _validate_input(
    frame: pd.DataFrame,
    recipes: tuple[ScreeningRecipe, ...],
    *,
    date_col: str,
    ticker_col: str,
    forward_return_col: str,
) -> pd.DataFrame:
    required = {date_col, ticker_col, forward_return_col}
    for recipe in recipes:
        required.update(term.feature for term in recipe.terms)
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"screening frame missing columns: {missing}")

    out = frame[list(required)].copy()
    out[date_col] = pd.to_datetime(out[date_col], errors="coerce").dt.normalize()
    out[ticker_col] = out[ticker_col].astype(str)
    if out[[date_col, ticker_col]].isna().any(axis=1).any():
        raise ValueError("screening frame contains null logical keys")
    if out.duplicated([date_col, ticker_col]).any():
        raise ValueError("screening frame contains duplicate logical keys")
    return out


def batch_screen(
    frame: pd.DataFrame,
    recipes: Iterable[ScreeningRecipe],
    *,
    date_col: str = "date",
    ticker_col: str = "stock_id",
    forward_return_col: str = "forward_return",
) -> pd.DataFrame:
    """Cheap candidate-level screening for many multi-feature recipes.

    Feature percentile ranks are computed once per feature/date and reused by
    every recipe. This stage deliberately excludes portfolio path mechanics,
    execution, sizing, and locked OOS. It is a funnel, not promotion evidence.
    """

    recipes = tuple(recipes)
    if not recipes:
        return pd.DataFrame(
            columns=[
                "recipe_id",
                "term_count",
                "selected_rows",
                "selected_dates",
                "mean_forward_return",
                "median_forward_return",
                "win_rate",
                "universe_mean_forward_return",
                "excess_mean_forward_return",
                "positive_year_fraction",
            ]
        )

    work = _validate_input(
        frame,
        recipes,
        date_col=date_col,
        ticker_col=ticker_col,
        forward_return_col=forward_return_col,
    )
    features = sorted(
        {term.feature for recipe in recipes for term in recipe.terms}
    )

    rank_cache: dict[str, pd.Series] = {}
    for feature in features:
        values = pd.to_numeric(work[feature], errors="coerce")
        rank_cache[feature] = values.groupby(work[date_col]).rank(
            method="average",
            pct=True,
        )

    forward_return = pd.to_numeric(work[forward_return_col], errors="coerce")
    universe_mean = float(forward_return.mean())

    rows: list[dict[str, object]] = []
    for recipe in recipes:
        score = pd.Series(0.0, index=work.index, dtype=float)
        total_weight = 0.0
        complete = pd.Series(True, index=work.index)
        for term in recipe.terms:
            ranked = rank_cache[term.feature]
            complete &= ranked.notna()
            directional = ranked if term.direction > 0 else 1.0 - ranked
            score += directional.fillna(0.0) * term.weight
            total_weight += term.weight
        score = score / total_weight

        candidate = work.loc[
            complete & forward_return.notna(),
            [date_col, ticker_col],
        ].copy()
        candidate["score"] = score.loc[candidate.index]
        candidate["forward_return"] = forward_return.loc[candidate.index]
        candidate = candidate.sort_values(
            [date_col, "score", ticker_col],
            ascending=[True, False, True],
        )
        group_size = candidate.groupby(date_col)[ticker_col].transform("size")
        rank_in_day = candidate.groupby(date_col).cumcount() + 1
        keep_n = group_size.map(
            lambda n: max(1, ceil(float(n) * recipe.selection_fraction))
        )
        selected = candidate.loc[rank_in_day <= keep_n].copy()

        selected_return = selected["forward_return"].astype(float)
        annual = selected.assign(
            year=pd.to_datetime(selected[date_col]).dt.year
        ).groupby("year")["forward_return"].mean()

        rows.append(
            {
                "recipe_id": recipe.recipe_id,
                "term_count": len(recipe.terms),
                "selected_rows": int(len(selected)),
                "selected_dates": int(selected[date_col].nunique()),
                "mean_forward_return": float(selected_return.mean()),
                "median_forward_return": float(selected_return.median()),
                "win_rate": float((selected_return > 0).mean()),
                "universe_mean_forward_return": universe_mean,
                "excess_mean_forward_return": float(
                    selected_return.mean() - universe_mean
                ),
                "positive_year_fraction": float((annual > 0).mean())
                if len(annual)
                else float("nan"),
            }
        )

    return pd.DataFrame(rows).sort_values(
        ["excess_mean_forward_return", "recipe_id"],
        ascending=[False, True],
    ).reset_index(drop=True)
