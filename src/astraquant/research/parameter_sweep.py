from __future__ import annotations

from dataclasses import dataclass
from itertools import product
import json
from pathlib import Path
from typing import Any

import pandas as pd

from astraquant.portfolio.policy import PortfolioPolicyConfig
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


class ResearchParameterSweepRunner:
    def __init__(self, engine: ResearchConfigEngine | None = None) -> None:
        self.engine = engine or ResearchConfigEngine()

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

        value_products = list(product(*(axis.values for axis in sweep.axes)))
        prepared: list[PreparedResearchRun] = []
        rows: list[dict[str, object]] = []

        for universe_path in sweep.universes:
            base_universe = universes[universe_path]
            for values in value_products:
                ucfg, scfg, ecfg = base_universe, base_signal, base_exit
                params: dict[str, object] = {}
                for axis, value in zip(sweep.axes, values):
                    ucfg, scfg, ecfg = _apply_axis(
                        universe=ucfg,
                        signal=scfg,
                        exit_config=ecfg,
                        target=axis.target,
                        value=value,
                    )
                    params[axis.target] = value

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
                result = self.engine.prepare_from_configs(
                    run_config=run_cfg,
                    universe_config=ucfg,
                    signal_config=scfg,
                    exit_config=ecfg,
                    panel=panel,
                    universe_context=universe_context,
                    signal_context=signal_context,
                    base_policy=base_policy,
                )
                prepared.append(result)
                rows.append(
                    {
                        "run_name": run_name,
                        "universe": ucfg.name,
                        "parameters": json.dumps(
                            params, ensure_ascii=False, sort_keys=True
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
            sweep_name=sweep.name,
            runs=tuple(prepared),
            summary=pd.DataFrame(rows),
            feature_cache_hits=self.engine.feature_cache.hits,
            feature_cache_misses=self.engine.feature_cache.misses,
        )
