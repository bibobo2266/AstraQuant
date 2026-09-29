from __future__ import annotations

from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import BaseModel

from astraquant.research.strategy_config import (
    BatchMatrixConfig,
    ExitConfig,
    SignalConfig,
    StrategyRunConfig,
    ThemeFile,
    UniverseConfig,
)


T = TypeVar("T", bound=BaseModel)


def _load_yaml(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    value = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"config must contain a YAML mapping: {p}")
    return value


def load_model(path: str | Path, model: type[T]) -> T:
    return model.model_validate(_load_yaml(path))


def load_universe_config(path: str | Path) -> UniverseConfig:
    return load_model(path, UniverseConfig)


def load_signal_config(path: str | Path) -> SignalConfig:
    return load_model(path, SignalConfig)


def load_exit_config(path: str | Path) -> ExitConfig:
    return load_model(path, ExitConfig)


def load_run_config(path: str | Path) -> StrategyRunConfig:
    return load_model(path, StrategyRunConfig)


def load_theme_file(path: str | Path) -> ThemeFile:
    return load_model(path, ThemeFile)


def load_batch_matrix_config(path: str | Path) -> BatchMatrixConfig:
    return load_model(path, BatchMatrixConfig)
