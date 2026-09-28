from datetime import date

import pytest
from pydantic import ValidationError

from astraquant.research.strategy_config import (
    AllPoolConfig,
    AvailabilityContract,
    BaseUniverseConfig,
    ComponentSpec,
    ExitConfig,
    ExitRuleConfig,
    SignalConfig,
    StrategyRunConfig,
    ThemeFile,
    UniverseConfig,
)


def test_universe_contract_freezes_candidate_base():
    cfg = UniverseConfig(
        name="all_liquid",
        base=BaseUniverseConfig(),
        pools=(AllPoolConfig(turnover_top_fraction=0.25),),
    )
    assert cfg.base.ticker_pattern == r"^[1-9]\d{3}$"
    assert cfg.base.min_close_twd == 10.0
    assert cfg.base.p2_060_exclusion_sha256.startswith("379d58f6")


def test_theme_membership_requires_dated_source():
    with pytest.raises(ValidationError):
        ThemeFile.model_validate(
            {
                "theme": "軍工航太",
                "members": [{"ticker": "2634", "source": "owner research"}],
            }
        )

    cfg = ThemeFile.model_validate(
        {
            "theme": "軍工航太",
            "members": [
                {
                    "ticker": "2634",
                    "from": "2022-02-24",
                    "to": None,
                    "source": "owner research note",
                }
            ],
        }
    )
    assert cfg.members[0].from_date == date(2022, 2, 24)


def test_signal_and_exit_are_independent_contracts():
    signal = SignalConfig(
        name="high_with_filters",
        trigger=ComponentSpec(type="N_SESSION_HIGH", params={"lookback": 250}),
        filters=(ComponentSpec(type="RSI", params={"min": 50}),),
    )
    exit_cfg = ExitConfig(
        name="stop_and_time",
        rules=(
            ExitRuleConfig(type="FIXED_STOP_TARGET", params={"stop_pct": 0.12}),
            ExitRuleConfig(type="TIME_EXIT", params={"sessions": 250}),
        ),
    )
    assert signal.trigger.type == "N_SESSION_HIGH"
    assert exit_cfg.rules[1].type == "TIME_EXIT"


def test_run_config_references_three_files_without_strategy_logic():
    cfg = StrategyRunConfig(
        run_name="example",
        universe="configs/universes/all_liquid.yaml",
        signal="configs/signals/high_250.yaml",
        exit="configs/exits/stop12_time250.yaml",
        execution_assumptions_id="taiwan-zero-cost-signal-isolation-v1",
    )
    assert cfg.report_trade_stats_first is True


def test_availability_contract_preserves_rows_and_t_plus_one():
    contract = AvailabilityContract()
    assert contract.universe_mask_must_preserve_rows is True
    assert contract.institutional_and_margin_usable == "T+1"
