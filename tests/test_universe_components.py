from pathlib import Path

import pandas as pd
import pytest

from astraquant.research.component_registry import UnsupportedComponentError
from astraquant.research.strategy_config import UniverseConfig
from astraquant.research.universe_engine import UniverseCompiler, UniverseContext


P2_SHA = "379d58f6a8aa06b1e020d56911930f4bc01861d3eeca109613d9e5b1e490d134"


def _base_rows():
    return [
        {
            "date": "2024-01-02",
            "stock_id": "2634",
            "close": 50.0,
            "Trading_money": 1_000_000.0,
            "observed_trade": True,
            "valid_ohlc": True,
        },
        {
            "date": "2024-01-02",
            "stock_id": "2330",
            "close": 100.0,
            "Trading_money": 5_000_000.0,
            "observed_trade": True,
            "valid_ohlc": True,
        },
        {
            "date": "2025-04-01",
            "stock_id": "2634",
            "close": 55.0,
            "Trading_money": 1_100_000.0,
            "observed_trade": True,
            "valid_ohlc": True,
        },
        {
            "date": "2025-04-01",
            "stock_id": "8033",
            "close": 40.0,
            "Trading_money": 900_000.0,
            "observed_trade": True,
            "valid_ohlc": True,
        },
    ]


def test_dated_theme_membership_changes_over_time(tmp_path: Path):
    theme_root = tmp_path / "themes"
    theme_root.mkdir()
    (theme_root / "軍工航太.yaml").write_text(
        """
schema_version: "1"
theme: 軍工航太
members:
  - ticker: "2634"
    from: 2022-02-24
    to: null
    source: "owner note"
  - ticker: "8033"
    from: 2023-06-01
    to: 2025-03-31
    source: "owner note"
""",
        encoding="utf-8",
    )
    cfg = UniverseConfig.model_validate(
        {
            "name": "theme_only",
            "pools": [
                {
                    "type": "INDUSTRY_THEME",
                    "groups": [
                        {
                            "mode": "THEME",
                            "themes": ["軍工航太"],
                            "combine": "OR",
                        }
                    ],
                }
            ],
        }
    )

    mask = UniverseCompiler().compile(
        cfg,
        pd.DataFrame(_base_rows()),
        UniverseContext(
            p2_060_excluded_tickers=frozenset(),
            p2_060_exclusion_sha256=P2_SHA,
            theme_root=theme_root,
        ),
    )

    selected = mask.frame[mask.frame["counts"]][["date", "stock_id"]]
    assert set(selected[selected["date"].eq(pd.Timestamp("2024-01-02"))]["stock_id"]) == {
        "2634"
    }
    assert set(selected[selected["date"].eq(pd.Timestamp("2025-04-01"))]["stock_id"]) == {
        "2634"
    }

    counts = mask.theme_member_counts_over_time()
    got = {
        row.date.strftime("%Y-%m-%d"): int(row.member_count)
        for row in counts.itertuples()
    }
    assert got == {"2024-01-02": 1, "2025-04-01": 1}


def test_stable_fundamental_and_earnings_pools_compose_with_and():
    rows = _base_rows()[:2]
    rows[0].update(
        {
            "downside_rs_ratio": 0.5,
            "rv60_percentile": 0.2,
            "max_drawdown_ratio_to_index": 0.9,
            "large_holder_fraction": 0.70,
            "large_holder_change_pp_250": 2.0,
            "consecutive_dividend_years": 8,
            "turnover_ratio_percentile": 0.3,
            "max_consecutive_loss_quarters_last4": 0,
            "debt_ratio": 0.40,
            "is_financial": False,
            "revenue_decline_streak_months": 1,
            "roe_4q_avg": 0.10,
            "eps_yoy_positive_streak": 4,
        }
    )
    rows[1].update(
        {
            "downside_rs_ratio": 0.9,
            "rv60_percentile": 0.8,
            "max_drawdown_ratio_to_index": 1.5,
            "large_holder_fraction": 0.40,
            "large_holder_change_pp_250": 7.0,
            "consecutive_dividend_years": 1,
            "turnover_ratio_percentile": 0.8,
            "max_consecutive_loss_quarters_last4": 2,
            "debt_ratio": 0.80,
            "is_financial": False,
            "revenue_decline_streak_months": 3,
            "roe_4q_avg": -0.02,
            "eps_yoy_positive_streak": 0,
        }
    )

    cfg = UniverseConfig.model_validate(
        {
            "name": "stacked",
            "combine": "AND",
            "pools": [
                {"type": "STABLE"},
                {"type": "FUNDAMENTAL_FLOOR"},
                {
                    "type": "EARNINGS_STREAK",
                    "consecutive_positive_eps_yoy_quarters": 3,
                },
            ],
        }
    )
    mask = UniverseCompiler().compile(
        cfg,
        pd.DataFrame(rows),
        UniverseContext(
            p2_060_excluded_tickers=frozenset(),
            p2_060_exclusion_sha256=P2_SHA,
        ),
    )

    selected = set(mask.frame.loc[mask.frame["counts"], "stock_id"])
    assert selected == {"2634"}


def test_missing_standardized_universe_feature_fails_loudly():
    cfg = UniverseConfig.model_validate(
        {"name": "stable", "pools": [{"type": "STABLE"}]}
    )
    with pytest.raises(ValueError, match="standardized columns"):
        UniverseCompiler().compile(
            cfg,
            pd.DataFrame(_base_rows()),
            UniverseContext(
                p2_060_excluded_tickers=frozenset(),
                p2_060_exclusion_sha256=P2_SHA,
            ),
        )


def test_official_grouping_fails_until_provider_exists():
    cfg = UniverseConfig.model_validate(
        {
            "name": "official_not_ready",
            "pools": [
                {
                    "type": "INDUSTRY_THEME",
                    "groups": [
                        {
                            "mode": "OFFICIAL",
                            "groups": ["電子上游"],
                        }
                    ],
                }
            ],
        }
    )

    with pytest.raises(UnsupportedComponentError, match="OFFICIAL"):
        UniverseCompiler().compile(
            cfg,
            pd.DataFrame(_base_rows()),
            UniverseContext(
                p2_060_excluded_tickers=frozenset(),
                p2_060_exclusion_sha256=P2_SHA,
            ),
        )
