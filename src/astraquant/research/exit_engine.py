from __future__ import annotations

from dataclasses import dataclass, replace

from astraquant.portfolio.policy import PortfolioPolicyConfig
from astraquant.research.component_registry import ComponentRegistry, UnsupportedComponentError
from astraquant.research.strategy_config import ExitConfig, ExitRuleConfig


@dataclass(frozen=True)
class CompiledCloseExitRule:
    type: str
    params: dict[str, object]


@dataclass(frozen=True)
class CompiledExitPlan:
    config_name: str
    stop_fraction: float | None
    max_hold_sessions: int | None
    close_exit_rules: tuple[CompiledCloseExitRule, ...] = ()

    def apply_to_policy(self, base: PortfolioPolicyConfig) -> PortfolioPolicyConfig:
        return replace(
            base,
            stop_fraction=self.stop_fraction,
            max_hold_sessions=self.max_hold_sessions,
        )


ExitRuleCompiler = callable


def _fixed_stop_target(rule: ExitRuleConfig) -> dict[str, object]:
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


def _time_exit(rule: ExitRuleConfig) -> dict[str, object]:
    if "sessions" not in rule.params:
        raise ValueError("TIME_EXIT requires sessions")
    sessions = int(rule.params["sessions"])
    if sessions <= 0:
        raise ValueError("TIME_EXIT sessions must be positive")
    return {"max_hold_sessions": sessions}


def _atr_trailing(rule: ExitRuleConfig) -> dict[str, object]:
    params = dict(rule.params)
    period = int(params.get("period", 21))
    multiplier = float(params.get("multiplier", 2.5))
    smoothing = str(params.get("smoothing", "WILDER")).upper()
    trigger_field = str(params.get("trigger_field", "CLOSE")).upper()
    execution = str(params.get("execution", "NEXT_OPEN")).upper()
    if period <= 0:
        raise ValueError("ATR_TRAILING period must be positive")
    if multiplier <= 0:
        raise ValueError("ATR_TRAILING multiplier must be positive")
    if smoothing != "WILDER":
        raise ValueError("ATR_TRAILING only supports WILDER smoothing")
    if trigger_field != "CLOSE":
        raise ValueError("ATR_TRAILING trigger_field must be CLOSE")
    if execution != "NEXT_OPEN":
        raise ValueError("ATR_TRAILING execution must be NEXT_OPEN")
    return {
        "close_rules": (
            CompiledCloseExitRule(
                type="ATR_TRAILING",
                params={
                    "period": period,
                    "multiplier": multiplier,
                    "smoothing": smoothing,
                    "trigger_field": trigger_field,
                    "execution": execution,
                },
            ),
        )
    }


def _ma_break(rule: ExitRuleConfig) -> dict[str, object]:
    params = dict(rule.params)
    window = int(params.get("window", 21))
    average = str(params.get("average", "SMA")).upper()
    require_cross = bool(params.get("require_cross", False))
    trigger_field = str(params.get("trigger_field", "CLOSE")).upper()
    execution = str(params.get("execution", "NEXT_OPEN")).upper()
    if window <= 0:
        raise ValueError("MA_BREAK window must be positive")
    if average != "SMA":
        raise ValueError("MA_BREAK currently supports SMA only")
    if require_cross:
        raise ValueError(
            "MA_BREAK require_cross=true is not supported by the VCP round1 close-state contract"
        )
    if trigger_field != "CLOSE":
        raise ValueError("MA_BREAK trigger_field must be CLOSE")
    if execution != "NEXT_OPEN":
        raise ValueError("MA_BREAK execution must be NEXT_OPEN")
    return {
        "close_rules": (
            CompiledCloseExitRule(
                type="MA_BREAK",
                params={
                    "window": window,
                    "average": average,
                    "require_cross": require_cross,
                    "trigger_field": trigger_field,
                    "execution": execution,
                },
            ),
        )
    }


def default_exit_registry() -> ComponentRegistry:
    registry = ComponentRegistry("exit")
    registry.register("FIXED_STOP_TARGET", _fixed_stop_target)
    registry.register("TIME_EXIT", _time_exit)
    registry.register("ATR_TRAILING", _atr_trailing)
    registry.register("MA_BREAK", _ma_break)
    return registry


class ExitCompiler:
    def __init__(self, registry: ComponentRegistry | None = None) -> None:
        self.registry = registry or default_exit_registry()

    def compile(self, config: ExitConfig) -> CompiledExitPlan:
        values: dict[str, float | int | None] = {
            "stop_fraction": None,
            "max_hold_sessions": None,
        }
        close_rules: list[CompiledCloseExitRule] = []
        seen_policy_values: set[str] = set()

        for rule in config.rules:
            handler = self.registry.get(rule.type)
            contribution = dict(handler(rule))
            contributed_close_rules = tuple(contribution.pop("close_rules", ()))
            close_rules.extend(contributed_close_rules)

            overlap = seen_policy_values & set(contribution)
            if overlap:
                raise ValueError(f"duplicate canonical exit setting: {sorted(overlap)}")
            for key, value in contribution.items():
                values[key] = value
                seen_policy_values.add(key)

        return CompiledExitPlan(
            config_name=config.name,
            stop_fraction=(
                None if values["stop_fraction"] is None else float(values["stop_fraction"])
            ),
            max_hold_sessions=(
                None
                if values["max_hold_sessions"] is None
                else int(values["max_hold_sessions"])
            ),
            close_exit_rules=tuple(close_rules),
        )
