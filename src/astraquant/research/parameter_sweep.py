from __future__ import annotations

from dataclasses import dataclass
from itertools import product
import json
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from astraquant.data.market_coordinates import SignalPriceSemantics
from astraquant.execution.service import SignalDeclaration
from astraquant.portfolio.policy import PortfolioPolicyConfig
from astraquant.research.candidates import candidates_from_signal_frame
from astraquant.research.config_engine import PreparedResearchRun, ResearchConfigEngine
from astraquant.research.config_io import (
    load_exit_config,
    load_parameter_sweep_config,
    load_signal_config,
    load_universe_config,
)
from astraquant.research.signal_engine import SignalContext
from astraquant.research.strategy_config import (
    ExitConfig,
    ParameterSweepConfig,
    SignalConfig,
    StrategyRunConfig,
    UniverseConfig,
)
from astraquant.research.universe_engine import UniverseContext


@dataclass(frozen=True)
class SweepPreparationResult:
    sweep_name: str
    runs: tuple[PreparedResearchRun, ...]
    summary: pd.DataFrame
    feature_cache_hits: int
    feature_cache_misses: int
    declared_combinations: int
    skipped_by_constraints: int


@dataclass(frozen=True)
class StreamedSweepRun:
    prepared: PreparedResearchRun
    universe: str
    parameters: dict[str, object]


@dataclass(frozen=True)
class SweepRunStream:
    sweep_name: str
    runs: Iterable[StreamedSweepRun]
    declared_combinations: int
    skipped_by_constraints: int


def _find_unique(items: list[dict[str, Any]], key: str, value: str, label: str) -> dict[str, Any]:
    matches = [item for item in items if str(item.get(key)) == value]
    if len(matches) != 1:
        raise ValueError(
            f"sweep target {label} requires exactly one matching component; "
            f"found {len(matches)} for {value}"
        )
    return matches[0]


def _apply_axis(
    *,
    universe: UniverseConfig,
    signal: SignalConfig,
    exit_config: ExitConfig,
    target: str,
    value: Any,
) -> tuple[UniverseConfig, SignalConfig, ExitConfig]:
    u = universe.model_dump(mode="python", by_alias=True)
    s = signal.model_dump(mode="python", by_alias=True)
    e = exit_config.model_dump(mode="python", by_alias=True)

    if "." not in target:
        raise ValueError(f"invalid sweep target: {target}")
    selector, param = target.rsplit(".", 1)

    if selector == "trigger":
        s["trigger"]["params"][param] = value
    elif selector.startswith("filter:"):
        component = selector.split(":", 1)[1]
        item = _find_unique(s["filters"], "type", component, "filter")
        item["params"][param] = value
    elif selector.startswith("ranking:"):
        component = selector.split(":", 1)[1]
        item = _find_unique(s["ranking"], "type", component, "ranking")
        item["params"][param] = value
    elif selector.startswith("exit:"):
        component = selector.split(":", 1)[1]
        item = _find_unique(e["rules"], "type", component, "exit")
        item["params"][param] = value
    elif selector.startswith("universe:"):
        component = selector.split(":", 1)[1]
        item = _find_unique(u["pools"], "type", component, "universe")
        item[param] = value
    else:
        raise ValueError(
            "unsupported sweep target root; use trigger.<param>, "
            "filter:<TYPE>.<param>, ranking:<TYPE>.<param>, "
            "exit:<TYPE>.<param>, or universe:<TYPE>.<param>"
        )

    return (
        UniverseConfig.model_validate(u),
        SignalConfig.model_validate(s),
        ExitConfig.model_validate(e),
    )


def _constraints_pass(sweep: ParameterSweepConfig, params: dict[str, object]) -> bool:
    for constraint in sweep.constraints:
        if constraint.type == "STRICTLY_INCREASING":
            values = []
            for target in constraint.targets:
                if target not in params:
                    raise ValueError(
                        f"sweep constraint target is not an axis: {target}"
                    )
                values.append(float(params[target]))
            if any(a >= b for a, b in zip(values, values[1:])):
                return False
        else:
            raise ValueError(f"unsupported sweep constraint: {constraint.type}")
    return True


class ResearchParameterSweepRunner:
    def __init__(self, engine: ResearchConfigEngine | None = None) -> None:
        self.engine = engine or ResearchConfigEngine()

    def stream_sweep(
        self,
        *,
        sweep_config_path: str | Path,
        root: str | Path,
        panel: pd.DataFrame,
        universe_context: UniverseContext,
        signal_context: SignalContext,
        base_policy: PortfolioPolicyConfig,
    ) -> SweepRunStream:
        root_path = Path(root).resolve()
        sweep: ParameterSweepConfig = load_parameter_sweep_config(sweep_config_path)
        base_signal = load_signal_config(
            self.engine._resolve(root_path, sweep.signal)
        )
        base_exit = load_exit_config(
            self.engine._resolve(root_path, sweep.exit)
        )
        universes = {
            path: load_universe_config(self.engine._resolve(root_path, path))
            for path in sweep.universes
        }

        raw_products = list(product(*(axis.values for axis in sweep.axes)))
        legal_products: list[tuple[tuple[object, ...], dict[str, object]]] = []
        invalid_products = 0
        for values in raw_products:
            params = {
                axis.target: value
                for axis, value in zip(sweep.axes, values)
            }
            if _constraints_pass(sweep, params):
                legal_products.append((values, params))
            else:
                invalid_products += 1

        skipped_by_constraints = invalid_products * len(sweep.universes)

        def generate() -> Iterable[StreamedSweepRun]:
            mask_cache: dict[str, object] = {}
            signal_panel_cache: dict[str, pd.DataFrame] = {}

            for universe_path in sweep.universes:
                base_universe = universes[universe_path]
                for values, raw_params in legal_products:
                    ucfg, scfg, ecfg = base_universe, base_signal, base_exit
                    params = dict(raw_params)
                    for axis, value in zip(sweep.axes, values):
                        ucfg, scfg, ecfg = _apply_axis(
                            universe=ucfg,
                            signal=scfg,
                            exit_config=ecfg,
                            target=axis.target,
                            value=value,
                        )

                    universe_key = ucfg.model_dump_json(
                        by_alias=True,
                        exclude_none=False,
                    )
                    if universe_key not in mask_cache:
                        mask_cache[universe_key] = self.engine.universe_compiler.compile(
                            ucfg,
                            panel,
                            universe_context,
                        )
                        signal_panel_cache[universe_key] = (
                            self.engine.signal_evaluator.prepare_panel(
                                panel,
                                mask_cache[universe_key],
                            )
                        )
                    mask = mask_cache[universe_key]
                    prepared_panel = signal_panel_cache[universe_key]

                    signal_plan = self.engine.signal_compiler.compile(scfg)
                    signal_frame = self.engine.signal_evaluator.evaluate_prepared(
                        signal_plan,
                        prepared_panel,
                        signal_context,
                    )
                    exit_plan = self.engine.exit_compiler.compile(ecfg)
                    policy = exit_plan.apply_to_policy(base_policy)

                    param_key = ",".join(
                        f"{key}={params[key]}" for key in sorted(params)
                    )
                    run_name = (
                        f"{sweep.name}__{ucfg.name}__"
                        + param_key.replace("/", "_").replace(" ", "")
                    )
                    run_cfg = StrategyRunConfig(
                        run_name=run_name,
                        universe=universe_path,
                        signal=sweep.signal,
                        exit=sweep.exit,
                        execution_assumptions_id=sweep.execution_assumptions_id,
                    )
                    declaration = SignalDeclaration(
                        source=f"CONFIG:{scfg.name}",
                        price_semantics=SignalPriceSemantics.SCALE_SENSITIVE,
                    )
                    candidates = candidates_from_signal_frame(
                        signal_frame,
                        declaration=declaration,
                    )
                    prepared = PreparedResearchRun(
                        run_config=run_cfg,
                        universe_config=ucfg,
                        signal_config=scfg,
                        exit_config=ecfg,
                        universe_mask=mask,
                        signal_frame=signal_frame,
                        candidates=candidates,
                        signal_plan=signal_plan,
                        exit_plan=exit_plan,
                        portfolio_policy=policy,
                        feature_cache_hits=self.engine.feature_cache.hits,
                        feature_cache_misses=self.engine.feature_cache.misses,
                    )
                    yield StreamedSweepRun(
                        prepared=prepared,
                        universe=ucfg.name,
                        parameters=params,
                    )

        return SweepRunStream(
            sweep_name=sweep.name,
            runs=generate(),
            declared_combinations=sweep.combination_count,
            skipped_by_constraints=skipped_by_constraints,
        )

    def prepare_sweep(
        self,
        *,
        sweep_config_path: str | Path,
        root: str | Path,
        panel: pd.DataFrame,
        universe_context: UniverseContext,
        signal_context: SignalContext,
        base_policy: PortfolioPolicyConfig,
    ) -> SweepPreparationResult:
        stream = self.stream_sweep(
            sweep_config_path=sweep_config_path,
            root=root,
            panel=panel,
            universe_context=universe_context,
            signal_context=signal_context,
            base_policy=base_policy,
        )
        prepared: list[PreparedResearchRun] = []
        rows: list[dict[str, object]] = []

        for item in stream.runs:
            result = item.prepared
            prepared.append(result)
            rows.append(
                {
                    "run_name": result.run_config.run_name,
                    "universe": item.universe,
                    "parameters": json.dumps(
                        item.parameters, ensure_ascii=False, sort_keys=True
                    ),
                    "universe_rows_counting": int(
                        result.universe_mask.frame["counts"].sum()
                    ),
                    "signal_candidates": int(
                        result.signal_frame["counts_as_candidate"].sum()
                    ),
                    "feature_cache_hits": result.feature_cache_hits,
                    "feature_cache_misses": result.feature_cache_misses,
                }
            )

        return SweepPreparationResult(
            sweep_name=stream.sweep_name,
            runs=tuple(prepared),
            summary=pd.DataFrame(rows),
            feature_cache_hits=self.engine.feature_cache.hits,
            feature_cache_misses=self.engine.feature_cache.misses,
            declared_combinations=stream.declared_combinations,
            skipped_by_constraints=stream.skipped_by_constraints,
        )
