from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from astraquant.research.baseline_60d_exploration import (
    BaselineExplorationError,
    FROZEN_METHOD,
    build_synthetic_fixture,
    load_eligibility_table,
    load_frozen_method_config,
    qualify_candidates,
    run_synthetic_exploration,
)
from astraquant.research.feature_panel_integration import sha256_file


METHOD_CONFIG = "configs/research/baseline_60d_breakout_v1/exploration.yaml"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_frozen_method_config_matches_single_approved_baseline():
    loaded = load_frozen_method_config(_repo_root() / METHOD_CONFIG)
    assert loaded == FROZEN_METHOD
    assert loaded["entry"]["lookback"] == 60
    assert loaded["exit"]["atr_period"] == 14
    assert loaded["exit"]["low_window"] == 20
    assert loaded["costs"] == {
        "buy_fee_bps": 14.25,
        "sell_fee_bps_including_tax": 44.25,
        "adverse_slippage_bps_each_side": 10.0,
        "settlement_lag_sessions": 2,
    }
    assert loaded["method_contract"]["cross_stock_capital_competition"] is False
    assert loaded["formal_research_status"] == "BLOCKED"
    assert "capital_constrained_max_positions" in loaded["unfrozen_for_real_e1"]


def test_synthetic_exploration_full_entry_report_and_costs(tmp_path):
    fixture = build_synthetic_fixture(tmp_path / "fixture")
    output = tmp_path / "output"

    artifacts = run_synthetic_exploration(
        repo_root=_repo_root(),
        fixture_root=fixture,
        output_dir=output,
        method_config_path=METHOD_CONFIG,
    )

    report = artifacts.report
    assert report["mode"] == "SYNTHETIC_FIXTURE"
    assert report["formal_research_status"] == "BLOCKED"

    # Original row denominator is preserved. No UNKNOWN/BLOCKED row is
    # zero-filled or silently removed from the population audit.
    assert report["population"]["row_denominator"] == 16 * 64
    assert report["population"]["unique_tickers"] == 16
    assert report["population"]["status_counts"] == {
        "ELIGIBLE": 15 * 64,
        "BLOCKED": 64,
    }
    assert report["population"]["reason_counts"]["ECONOMIC_CONTENT_UNRESOLVED"] == 64

    # Four frozen-method candidates: three executable, one explicit economic
    # content block. The blocked candidate never becomes a fill.
    assert report["candidate_funnel"]["signal_candidates"] == 4
    assert report["candidate_funnel"]["eligible_candidates"] == 3
    assert report["candidate_funnel"]["status_counts"] == {
        "ELIGIBLE": 3,
        "BLOCKED": 1,
    }
    assert (
        report["candidate_funnel"]["reason_counts"][
            "ECONOMIC_CONTENT_UNRESOLVED"
        ]
        == 1
    )
    blocked = artifacts.candidate_funnel[
        artifacts.candidate_funnel["stock_id"].eq("2317")
    ].iloc[0]
    assert blocked["eligibility_status"] == "BLOCKED"

    # Candidate cohort is independent-by-ticker and remains separate from
    # capacity-constrained portfolio results.
    candidate_metrics = report["candidate_cohort"]["metrics"]
    capital_metrics = report["capital_constrained"]["metrics"]
    assert candidate_metrics["n_closed"] == 2
    assert candidate_metrics["n_open"] == 1
    assert candidate_metrics["win_rate"] == pytest.approx(0.5)
    assert capital_metrics["n_closed"] == 2
    assert capital_metrics["n_open"] == 0
    assert report["capital_constrained"]["entries_executed"] == 2
    assert report["capital_constrained"]["capacity_rejections"] == 1

    assert set(artifacts.candidate_trades["stock_id"]) == {"2330", "2454"}
    assert "3008" in set(
        artifacts.open_positions.loc[
            artifacts.open_positions["run_label"].eq("CANDIDATE_COHORT"),
            "stock_id",
        ]
    )
    assert "2317" not in set(artifacts.candidate_trades["stock_id"])
    assert "2317" not in set(artifacts.open_positions["stock_id"])

    # Fee+tax and slippage are applied exactly once by the canonical fill
    # factory. Compare report return against the one-pass fill economics.
    by_ticker = artifacts.candidate_trades.set_index("stock_id")
    entry_fill = 100.0 * 1.001
    entry_cost = entry_fill * (1.0 + 14.25 / 10_000.0)
    expected_2330 = (
        105.0 * 0.999 * (1.0 - 44.25 / 10_000.0) - entry_cost
    ) / entry_cost
    expected_2454 = (
        95.0 * 0.999 * (1.0 - 44.25 / 10_000.0) - entry_cost
    ) / entry_cost
    assert by_ticker.loc["2330", "net_return"] == pytest.approx(expected_2330)
    assert by_ticker.loc["2454", "net_return"] == pytest.approx(expected_2454)

    # MFE/MAE exists only as a diagnostic surface.
    assert report["mfe_mae"]["role"] == "DIAGNOSTIC_ONLY"
    assert report["mfe_mae"]["status_counts"] == {"OK": 4}
    assert artifacts.mfe_mae["mfe"].notna().all()
    assert artifacts.mfe_mae["mae"].notna().all()

    expected_files = {
        "report.json",
        "candidate_trades.csv",
        "capital_constrained_trades.csv",
        "open_positions.csv",
        "eligibility_audit.csv",
        "candidate_funnel.csv",
        "mfe_mae_diagnostics.csv",
    }
    assert expected_files == {path.name for path in output.iterdir()}
    stored = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert stored["candidate_funnel"] == report["candidate_funnel"]


def test_missing_candidate_eligibility_is_explicit_unknown_not_zero(tmp_path):
    fixture = build_synthetic_fixture(tmp_path / "fixture")
    table_path = fixture / "eligibility.csv"
    manifest_path = fixture / "eligibility_manifest.json"
    table = pd.read_csv(table_path, dtype={"stock_id": str})
    signal_date = sorted(pd.to_datetime(table["date"]).dt.normalize().unique())[61]
    keep = ~(
        table["stock_id"].eq("3008")
        & pd.to_datetime(table["date"]).dt.normalize().eq(signal_date)
    )
    table = table.loc[keep].copy()
    table.to_csv(table_path, index=False)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["row_count"] = len(table)
    manifest["table_sha256"] = sha256_file(table_path)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    eligibility = load_eligibility_table(
        table_path=table_path,
        manifest_path=manifest_path,
    )
    candidates = pd.DataFrame(
        [
            {
                "signal_date": signal_date,
                "stock_id": "3008",
            }
        ]
    )
    out = qualify_candidates(candidates, eligibility)
    assert out.iloc[0]["eligibility_status"] == "UNKNOWN"
    assert out.iloc[0]["reason_code"] == "MISSING_ELIGIBILITY_ROW"
    assert len(eligibility.frame) == 16 * 64 - 1


def test_eligibility_checksum_tamper_fails_closed(tmp_path):
    fixture = build_synthetic_fixture(tmp_path / "fixture")
    table_path = fixture / "eligibility.csv"
    table = pd.read_csv(table_path, dtype={"stock_id": str})
    table.loc[0, "reason_code"] = "TAMPERED"
    table.to_csv(table_path, index=False)

    with pytest.raises(BaselineExplorationError, match="checksum mismatch"):
        load_eligibility_table(
            table_path=table_path,
            manifest_path=fixture / "eligibility_manifest.json",
        )


def test_execution_source_checksum_tamper_fails_before_simulation(tmp_path):
    fixture = build_synthetic_fixture(tmp_path / "fixture")
    raw_path = fixture / "source/raw/prices_raw_2020.parquet"
    raw = pd.read_parquet(raw_path)
    raw.loc[0, "open"] = 999.0
    raw.to_parquet(raw_path, index=False)

    with pytest.raises(BaselineExplorationError, match="source file checksum mismatch"):
        run_synthetic_exploration(
            repo_root=_repo_root(),
            fixture_root=fixture,
            output_dir=tmp_path / "output",
            method_config_path=METHOD_CONFIG,
        )


@pytest.mark.parametrize("manifest_name", ["source_manifest.json", "eligibility_manifest.json"])
def test_synthetic_runner_rejects_non_fixture_scope(tmp_path, manifest_name):
    fixture = build_synthetic_fixture(tmp_path / "fixture")
    path = fixture / manifest_name
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["scope"] = "SOURCE_EVIDENCE"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(BaselineExplorationError, match="scope mismatch"):
        run_synthetic_exploration(
            repo_root=_repo_root(),
            fixture_root=fixture,
            output_dir=tmp_path / "output",
            method_config_path=METHOD_CONFIG,
        )
