from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import json

from .models import ExperimentSpec, Trial


class ExperimentRegistry:
    def __init__(self) -> None:
        self.experiments: dict[str, ExperimentSpec] = {}
        self.trials: list[Trial] = []

    def register_experiment(self, spec: ExperimentSpec) -> None:
        if spec.experiment_id in self.experiments:
            raise ValueError(f"Experiment already frozen: {spec.experiment_id}")
        self.experiments[spec.experiment_id] = spec

    def record_trial(self, trial: Trial) -> None:
        if trial.experiment_id not in self.experiments:
            raise ValueError(f"Unknown experiment: {trial.experiment_id}")
        self.trials.append(trial)

    def export_json(self, path: str | Path) -> None:
        payload = {
            "experiments": [asdict(x) for x in self.experiments.values()],
            "trials": [asdict(x) for x in self.trials],
        }
        Path(path).write_text(json.dumps(payload, default=str, indent=2), encoding="utf-8")
