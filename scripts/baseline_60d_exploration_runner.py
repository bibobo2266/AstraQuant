#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from astraquant.research.baseline_60d_exploration import (
    BaselineExplorationError,
    build_synthetic_fixture,
    run_synthetic_exploration,
)
from astraquant.research.baseline_60d_simulation import (
    BaselineSimulationContext,
    BaselineSimulationMode,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the frozen 60D breakout exploration preparation on an "
            "explicit synthetic fixture. FORMAL_RESEARCH remains blocked."
        )
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="AstraQuant repository root",
    )
    parser.add_argument(
        "--method-config",
        default="configs/research/baseline_60d_breakout_v1/exploration.yaml",
    )
    parser.add_argument(
        "--mode",
        choices=["SYNTHETIC_FIXTURE", "FORMAL_RESEARCH"],
        default="SYNTHETIC_FIXTURE",
    )
    parser.add_argument(
        "--fixture-root",
        required=True,
        help="Synthetic fixture directory",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Output directory for report/tables",
    )
    parser.add_argument(
        "--build-fixture",
        action="store_true",
        help="Build the deterministic synthetic fixture before running",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    mode = BaselineSimulationMode(args.mode)
    if mode is BaselineSimulationMode.FORMAL_RESEARCH:
        # Same canonical hard stop as the simulator path. Do this before
        # reading any fixture/source data so there is no synthetic fallback.
        BaselineSimulationContext(mode=mode).require_runnable()

    fixture_root = Path(args.fixture_root)
    if args.build_fixture:
        build_synthetic_fixture(fixture_root)
    if not fixture_root.exists():
        raise SystemExit(
            f"BLOCKED: synthetic fixture does not exist: {fixture_root}"
        )

    try:
        artifacts = run_synthetic_exploration(
            repo_root=Path(args.repo_root),
            fixture_root=fixture_root,
            output_dir=Path(args.output_dir),
            method_config_path=args.method_config,
        )
    except BaselineExplorationError as exc:
        raise SystemExit(f"BLOCKED: {exc}") from exc

    report = artifacts.report
    print(
        "SYNTHETIC_BASELINE_EXPLORATION_OK "
        f"candidates={report['candidate_funnel']['signal_candidates']} "
        f"eligible={report['candidate_funnel']['eligible_candidates']} "
        f"candidate_closed={report['candidate_cohort']['metrics']['n_closed']} "
        f"candidate_open={report['candidate_cohort']['metrics']['n_open']} "
        f"capital_closed={report['capital_constrained']['metrics']['n_closed']} "
        f"output={Path(args.output_dir).resolve()}"
    )


if __name__ == "__main__":
    main()
