from __future__ import annotations

from dataclasses import dataclass, replace

from astraquant.portfolio.policy import PortfolioPolicyConfig
from astraquant.research.component_registry import ComponentRegistry, UnsupportedComponentError
from astraquant.research.strategy_config import ExitConfig, ExitRuleConfig


@dataclass(frozen=True)
class CompiledExitPlan:
    config_name: str
    stop_fraction: float
    max_hold_sessions: int

    def apply_to_policy(self, base: PortfolioPolicyConfig) -> PortfolioPolicyConfig:
        return replace(
            base,
            stop_fraction=self.stop_fraction,
            max_hold_sessions=self.max_hold_sessions,
        )


ExitRuleCompiler = callable


def _fixed_stop_target(rule: ExitRuleConfig) -> dict[str, float | int]:
    params = rule.params
    if "stop_pct" not in params:
        raise ValueError("FIXED_STOP_TARGET requires stop_pct")
    stop = float(params["stop_pct"])
    if not 0 < stop < 1:
        raise ValueError("stop_pct must be in (0, 1)")
    target = params.get("target_pct")
    if target is not None:
        raise UnsupportedComponentError(
            "fixed profit target is declared by schema but not implemented in "
            "the current canonical policy; use target_pct: null until evaluator exists"
        )
    return {"stop_fraction": stop}


def _time_exit(rule: ExitRuleConfig) -> dict[str, float | int]:
    if "sessions" not in rule.params:
        raise ValueError("TIME_EXIT requires sessions")
    sessions = int(rule.params["sessions"])
    if sessions <= 0:
        raise ValueError("TIME_EXIT sessions must be positive")
    return {"max_hold_sessions": sessions}


def default_exit_registry() -> ComponentRegistry:
    registry = ComponentRegistry("exit")
    registry.register("FIXED_STOP_TARGET", _fixed_stop_target)
    registry.register("TIME_EXIT", _time_exit)
    return registry


class ExitCompiler:
    def __init__(self, registry: ComponentRegistry | None = None) -> None:
        self.registry = registry or default_exit_registry()

    def compile(self, config: ExitConfig) -> CompiledExitPlan:
        values: dict[str, float | int] = {}
        for rule in config.rules:
            handler = self.registry.get(rule.type)
            contribution = handler(rule)
            overlap = set(values) & set(contribution)
            if overlap:
                raise ValueError(f"duplicate canonical exit setting: {sorted(overlap)}")
            values.update(contribution)

        if "stop_fraction" not in values:
            raise UnsupportedComponentError(
                "current canonical portfolio policy requires a fixed stop; "
                "an exit-only strategy without fixed stop needs policy support first"
            )
        if "max_hold_sessions" not in values:
            raise UnsupportedComponentError(
                "current canonical portfolio policy requires max-hold/time exit"
            )
        return CompiledExitPlan(
            config_name=config.name,
            stop_fraction=float(values["stop_fraction"]),
            max_hold_sessions=int(values["max_hold_sessions"]),
        )
