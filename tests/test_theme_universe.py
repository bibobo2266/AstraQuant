from pathlib import Path

import pandas as pd
import pytest

from astraquant.research.component_registry import UnsupportedComponentError
from astraquant.research.strategy_config import UniverseConfig
from astraquant.research.universe_engine import UniverseCompiler, UniverseContext


P2_SHA = "379d58f6a8aa06b1e020d56911930f4bc01861d3eeca109613d9e5b1e490d134"


def _panel():
    rows = []
    for day in ["2024-01-02", "2025-04-01"]:
        for ticker in ["2634", "8033", "2330"]:
            rows.append(
                {
                    "date": day,
                    "stock_id": ticker,
                    "close": 50.0,
                    "Trading_money": 1_000_000.0,
                    "observed_trade": True,
                    "valid_ohlc": True,
                }
            )
    return pd.DataFrame(rows)


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
        _panel(),
        UniverseContext(
            p2_060_excluded_tickers=frozenset(),
            p2_060_exclusion_sha256=P2_SHA,
            theme_root=theme_root,
        ),
    )

    selected = mask.frame[mask.frame["counts"]][["date", "stock_id"]]
    assert set(selected[selected["date"].eq(pd.Timestamp("2024-01-02"))]["stock_id"]) == {
        "2634",
        "8033",
    }
    assert set(selected[selected["date"].eq(pd.Timestamp("2025-04-01"))]["stock_id"]) == {
        "2634"
    }

    counts = mask.theme_member_counts_over_time()
    got = {
        row.date.strftime("%Y-%m-%d"): int(row.member_count)
        for row in counts.itertuples()
    }
    assert got == {"2024-01-02": 2, "2025-04-01": 1}


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
            _panel(),
            UniverseContext(
                p2_060_excluded_tickers=frozenset(),
                p2_060_exclusion_sha256=P2_SHA,
            ),
        )
