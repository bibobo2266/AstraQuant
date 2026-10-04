from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import pyarrow.parquet as pq
import yaml


class AvailabilityStatus(str, Enum):
    VERIFIED = "VERIFIED"
    ASSUMPTION_ONLY = "ASSUMPTION_ONLY"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"


_STATUS_SEVERITY = {
    AvailabilityStatus.VERIFIED: 0,
    AvailabilityStatus.ASSUMPTION_ONLY: 1,
    AvailabilityStatus.UNKNOWN: 2,
    AvailabilityStatus.UNAVAILABLE: 3,
}


class EligibilityEvidenceScope(str, Enum):
    INTEGRITY_ONLY = "INTEGRITY_ONLY"
    SYNTHETIC_FIXTURE = "SYNTHETIC_FIXTURE"


class FeaturePanelIntegrationError(ValueError):
    pass


def _canonicalize(value: Any) -> Any:
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, dict):
        return {
            str(key): _canonicalize(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    return value


def stable_object_sha256(value: Any) -> str:
    payload = json.dumps(
        _canonicalize(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def dataframe_sha256(frame: pd.DataFrame) -> str:
    """Deterministic in-process content identity for research data frames.

    This is an integrity/fingerprint mechanism, not a malicious-tamper security
    boundary. It avoids Python object identity and binds values, column names,
    dtypes, and row order.
    """
    if frame.columns.duplicated().any():
        raise FeaturePanelIntegrationError(
            "cannot fingerprint dataframe with duplicate column names"
        )
    columns = sorted(str(column) for column in frame.columns)
    work = frame.loc[:, columns].copy()
    digest = hashlib.sha256()
    metadata = {
        "columns": columns,
        "dtypes": [str(work[column].dtype) for column in columns],
        "rows": len(work),
    }
    digest.update(
        json.dumps(
            metadata,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    hashed = pd.util.hash_pandas_object(
        work,
        index=False,
        categorize=False,
    )
    digest.update(hashed.to_numpy(dtype="uint64", copy=False).tobytes())
    return digest.hexdigest()


@dataclass(frozen=True)
class VerifiedArtifactEvidence:
    year: int
    path: str
    filename: str
    sha256: str
    rows: int | None


@dataclass(frozen=True)
class VerifiedFeatureEvidence:
    column: str
    kind: str
    required: bool
    warmup_sessions: int | None
    dependencies: tuple[str, ...]
    status: AvailabilityStatus


@dataclass(frozen=True)
class FeaturePanelEligibilityEvidence:
    schema_version: str
    scope: EligibilityEvidenceScope
    evidence_source: str
    integration_name: str
    integration_config_sha256: str
    manifest_path: str
    manifest_sha256: str
    artifact_name: str
    source_revision: str
    formula_version: str
    epoch: str
    manifest_period_start: str
    manifest_period_end: str
    panel_date_start: str
    panel_date_end: str
    cutoff_contracts: tuple[str, ...]
    requested_features: tuple[VerifiedFeatureEvidence, ...]
    artifacts: tuple[VerifiedArtifactEvidence, ...]
    hydrated_panel_sha256: str
    audit_sha256: str
    evidence_sha256: str

    def payload_without_digest(self) -> dict[str, object]:
        payload = asdict(self)
        payload.pop("evidence_sha256", None)
        return payload

    def verify_self_digest(self) -> None:
        actual = stable_object_sha256(self.payload_without_digest())
        if actual != self.evidence_sha256:
            raise FeaturePanelIntegrationError(
                "feature eligibility evidence digest mismatch"
            )


@dataclass(frozen=True)
class FeatureRequest:
    column: str
    kind: str
    required: bool
    warmup_sessions: int | None
    dependencies: tuple[str, ...]
    status: AvailabilityStatus


@dataclass(frozen=True)
class FeaturePanelIntegrationConfig:
    name: str
    epoch: str
    manifest_path: Path
    expected_artifact_name: str
    expected_source_revision: str
    expected_formula_version: str
    expected_epoch: str
    strategy_required_status: AvailabilityStatus
    requested_features: tuple[FeatureRequest, ...]


@dataclass(frozen=True)
class FeaturePanelJoinResult:
    frame: pd.DataFrame
    audit: pd.DataFrame
    manifest: dict[str, object]
    evidence: FeaturePanelEligibilityEvidence


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def combine_availability_status(
    statuses: Iterable[AvailabilityStatus],
) -> AvailabilityStatus:
    values = list(statuses)
    if not values:
        return AvailabilityStatus.UNKNOWN
    return max(values, key=lambda x: _STATUS_SEVERITY[x])


def load_feature_panel_integration_config(
    path: str | Path,
) -> FeaturePanelIntegrationConfig:
    p = Path(path)
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    groups = raw.get("availability_groups", {})
    requested: list[FeatureRequest] = []
    for row in raw.get("requested_features", []):
        deps = tuple(str(x) for x in row.get("dependencies", []))
        statuses: list[AvailabilityStatus] = []
        for dep in deps:
            if dep not in groups:
                raise FeaturePanelIntegrationError(
                    f"availability dependency is not declared: {dep}"
                )
            statuses.append(AvailabilityStatus(str(groups[dep]["status"])))
        effective = combine_availability_status(statuses)
        expected = AvailabilityStatus(str(row["expected_status"]))
        if effective is not expected:
            raise FeaturePanelIntegrationError(
                f"availability status drift for {row['column']}: "
                f"derived={effective.value} expected={expected.value}"
            )
        kind = str(row.get("kind", "RAW")).upper()
        column = str(row["column"])
        if kind == "RAW" and column.endswith("_pct"):
            raise FeaturePanelIntegrationError(
                f"RAW feature request cannot target percentile column: {column}"
            )
        if kind == "PERCENTILE" and not column.endswith("_pct"):
            raise FeaturePanelIntegrationError(
                f"PERCENTILE feature request must use explicit *_pct column: {column}"
            )
        warmup = row.get("warmup_sessions")
        requested.append(
            FeatureRequest(
                column=column,
                kind=kind,
                required=bool(row.get("required", True)),
                warmup_sessions=None if warmup is None else int(warmup),
                dependencies=deps,
                status=effective,
            )
        )
    artifact = raw["artifact"]
    policy = raw["policy"]
    return FeaturePanelIntegrationConfig(
        name=str(raw["name"]),
        epoch=str(raw["epoch"]),
        manifest_path=Path(str(artifact["manifest_path"])),
        expected_artifact_name=str(artifact["artifact_name"]),
        expected_source_revision=str(artifact["source_revision"]),
        expected_formula_version=str(artifact["formula_version"]),
        expected_epoch=str(artifact["epoch"]),
        strategy_required_status=AvailabilityStatus(
            str(policy["strategy_required_status"])
        ),
        requested_features=tuple(requested),
    )


class FeaturePanelIntegrator:
    """Controlled exact-key hydration from the frozen layer-1 feature artifact.

    The integrator performs only a left join on (date, stock_id). It never
    recomputes features, fills missing values, changes the research epoch, or
    searches for a newer artifact. Strategy-mode hydration fails closed unless
    every required feature dependency has VERIFIED decision-cutoff evidence.
    """

    def __init__(
        self,
        *,
        config: FeaturePanelIntegrationConfig,
        artifact_root: str | Path,
        manifest_path: str | Path | None = None,
        verified_only: bool = True,
        evidence_scope: EligibilityEvidenceScope | str = (
            EligibilityEvidenceScope.INTEGRITY_ONLY
        ),
        evidence_source: str = "FeaturePanelIntegrator",
    ) -> None:
        self.config = config
        self.artifact_root = Path(artifact_root)
        self.manifest_path = (
            Path(manifest_path)
            if manifest_path is not None
            else config.manifest_path
        )
        self.verified_only = bool(verified_only)
        if isinstance(evidence_scope, EligibilityEvidenceScope):
            self.evidence_scope = evidence_scope
        elif isinstance(evidence_scope, str):
            try:
                self.evidence_scope = EligibilityEvidenceScope(
                    evidence_scope.strip().upper()
                )
            except ValueError as exc:
                raise FeaturePanelIntegrationError(
                    f"unknown evidence_scope: {evidence_scope!r}"
                ) from exc
        else:
            raise FeaturePanelIntegrationError(
                "evidence_scope must be EligibilityEvidenceScope or string"
            )
        if not isinstance(evidence_source, str) or not evidence_source.strip():
            raise FeaturePanelIntegrationError(
                "evidence_source must be a non-empty string"
            )
        self.evidence_source = evidence_source.strip()

    def _load_manifest(self) -> dict[str, object]:
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        checks = {
            "artifact_name": (
                manifest.get("artifact_name"),
                self.config.expected_artifact_name,
            ),
            "source_revision": (
                manifest.get("source_revision"),
                self.config.expected_source_revision,
            ),
            "formula_version": (
                manifest.get("formula_version"),
                self.config.expected_formula_version,
            ),
            "epoch": (manifest.get("epoch"), self.config.expected_epoch),
        }
        for name, (actual, expected) in checks.items():
            if actual != expected:
                raise FeaturePanelIntegrationError(
                    f"feature artifact {name} mismatch: actual={actual} "
                    f"expected={expected}"
                )
        return manifest

    @staticmethod
    def _normalize_panel(panel: pd.DataFrame) -> pd.DataFrame:
        required = {"date", "stock_id"}
        missing = required - set(panel.columns)
        if missing:
            raise FeaturePanelIntegrationError(
                f"canonical panel missing logical keys: {sorted(missing)}"
            )
        out = panel.copy()
        out["date"] = pd.to_datetime(
            out["date"], errors="coerce"
        ).dt.normalize()
        out["stock_id"] = out["stock_id"].astype(str)
        if out[["date", "stock_id"]].isna().any(axis=1).any():
            raise FeaturePanelIntegrationError(
                "canonical panel contains null logical keys"
            )
        if out.duplicated(["date", "stock_id"]).any():
            raise FeaturePanelIntegrationError(
                "canonical panel contains duplicate logical keys"
            )
        return out

    def _enforce_epoch(
        self,
        panel: pd.DataFrame,
        manifest: dict[str, object],
    ) -> None:
        period = manifest.get("period")
        if not isinstance(period, list) or len(period) != 2:
            raise FeaturePanelIntegrationError(
                "feature manifest has no closed E1 period"
            )
        start = pd.Timestamp(period[0]).normalize()
        end = pd.Timestamp(period[1]).normalize()
        outside = ~panel["date"].between(start, end, inclusive="both")
        if outside.any():
            sample = panel.loc[
                outside, ["date", "stock_id"]
            ].head(3)
            raise FeaturePanelIntegrationError(
                "feature hydration is E1-only; outside-period keys found: "
                + repr(sample.to_dict("records"))
            )

    def _enforce_availability(self) -> None:
        if not self.verified_only:
            return
        blocked = [
            f"{r.column}:{r.status.value}"
            for r in self.config.requested_features
            if r.required
            and r.status is not self.config.strategy_required_status
        ]
        if blocked:
            raise FeaturePanelIntegrationError(
                "required feature inputs are not VERIFIED for strategy use: "
                + ", ".join(blocked)
            )

    @staticmethod
    def _year_entry(
        manifest: dict[str, object],
        year: int,
    ) -> dict[str, object]:
        target = f"stock_features_{year}.parquet"
        for entry in manifest.get("stock_files", []):
            if Path(str(entry["path"])).name == target:
                return entry
        raise FeaturePanelIntegrationError(
            f"feature manifest has no stock artifact for year {year}"
        )

    def _resolve_artifact_file(
        self,
        entry: dict[str, object],
    ) -> Path:
        name = Path(str(entry["path"])).name
        candidates = [
            self.artifact_root / name,
            self.artifact_root / str(entry["path"]),
        ]
        for path in candidates:
            if path.exists():
                return path
        raise FeaturePanelIntegrationError(
            f"feature artifact file is unavailable: {name}"
        )

    def _load_year(
        self,
        manifest: dict[str, object],
        year: int,
    ) -> tuple[pd.DataFrame, VerifiedArtifactEvidence]:
        entry = self._year_entry(manifest, year)
        path = self._resolve_artifact_file(entry)
        digest = sha256_file(path)
        expected = str(entry["sha256"])
        if digest != expected:
            raise FeaturePanelIntegrationError(
                f"feature artifact checksum mismatch for {path.name}: "
                f"actual={digest} expected={expected}"
            )

        requested = [r.column for r in self.config.requested_features]
        schema = pq.ParquetFile(path).schema.names
        missing = [c for c in requested if c not in schema]
        if missing:
            raise FeaturePanelIntegrationError(
                f"requested feature columns missing from {path.name}: {missing}"
            )
        metadata_candidates = [
            "date",
            "stock_id",
            "available_at_date",
            "available_at_rule",
            "bars_seen",
            "source_available_at",
        ]
        columns = list(
            dict.fromkeys(
                [c for c in metadata_candidates if c in schema]
                + requested
            )
        )
        out = pd.read_parquet(path, columns=columns)
        out["date"] = pd.to_datetime(
            out["date"], errors="coerce"
        ).dt.normalize()
        out["stock_id"] = out["stock_id"].astype(str)
        if out[["date", "stock_id"]].isna().any(axis=1).any():
            raise FeaturePanelIntegrationError(
                f"feature artifact {path.name} has null logical keys"
            )
        if out.duplicated(["date", "stock_id"]).any():
            raise FeaturePanelIntegrationError(
                f"feature artifact {path.name} has duplicate logical keys"
            )
        rows_raw = entry.get("rows")
        rows = None if rows_raw is None else int(rows_raw)
        return out, VerifiedArtifactEvidence(
            year=int(year),
            path=str(path.resolve()),
            filename=path.name,
            sha256=digest,
            rows=rows,
        )

    def hydrate(self, panel: pd.DataFrame) -> FeaturePanelJoinResult:
        manifest = self._load_manifest()
        work = self._normalize_panel(panel)
        self._enforce_epoch(work, manifest)
        self._enforce_availability()

        requested = [r.column for r in self.config.requested_features]
        companion_columns: list[str] = []
        for request in self.config.requested_features:
            companion_columns.extend(
                [
                    f"__feature_availability__{request.column}",
                    f"__feature_missing_reason__{request.column}",
                ]
            )
        conflicts = sorted(
            (set(requested) | set(companion_columns)) & set(work.columns)
        )
        if conflicts:
            raise FeaturePanelIntegrationError(
                f"feature hydration column conflict: {conflicts}"
            )

        work = work.copy()
        work["__feature_join_order"] = range(len(work))
        years = sorted(work["date"].dt.year.unique().tolist())
        loaded_years = [
            self._load_year(manifest, int(year)) for year in years
        ]
        feature_parts = [item[0] for item in loaded_years]
        artifact_evidence = tuple(item[1] for item in loaded_years)
        features = pd.concat(feature_parts, ignore_index=True)
        features = features.merge(
            work[["date", "stock_id"]],
            on=["date", "stock_id"],
            how="inner",
            validate="one_to_one",
        )
        features["__artifact_row_present"] = True

        before = len(work)
        joined = work.merge(
            features,
            on=["date", "stock_id"],
            how="left",
            validate="one_to_one",
            suffixes=("", "__feature"),
        )
        if len(joined) != before:
            raise FeaturePanelIntegrationError(
                "feature hydration changed canonical panel row count"
            )
        joined = joined.sort_values(
            "__feature_join_order", kind="stable"
        ).drop(columns=["__feature_join_order"])

        if "available_at_date" in joined.columns:
            declared = pd.to_datetime(
                joined["available_at_date"], errors="coerce"
            ).dt.normalize()
            future = declared.gt(joined["date"])
            if future.fillna(False).any():
                sample = joined.loc[
                    future.fillna(False),
                    ["date", "stock_id", "available_at_date"],
                ].head(3)
                raise FeaturePanelIntegrationError(
                    "feature row declares availability after its logical date: "
                    + repr(sample.to_dict("records"))
                )

        if (
            "source_available_at" in joined.columns
            and "__decision_cutoff_at" in joined.columns
        ):
            source_at = pd.to_datetime(
                joined["source_available_at"], errors="coerce"
            )
            cutoff = pd.to_datetime(
                joined["__decision_cutoff_at"], errors="coerce"
            )
            late = (
                source_at.notna()
                & cutoff.notna()
                & source_at.ge(cutoff)
            )
            if late.any():
                sample = joined.loc[
                    late,
                    [
                        "date",
                        "stock_id",
                        "source_available_at",
                        "__decision_cutoff_at",
                    ],
                ].head(3)
                raise FeaturePanelIntegrationError(
                    "feature input is not available before decision cutoff: "
                    + repr(sample.to_dict("records"))
                )

        present = joined[
            "__artifact_row_present"
        ].fillna(False).astype(bool)
        audit_rows: list[dict[str, object]] = []
        for request in self.config.requested_features:
            col = request.column
            reason = pd.Series(
                "", index=joined.index, dtype="string"
            )
            reason.loc[~present] = "ARTIFACT_ROW_ABSENT"
            value_missing = present & joined[col].isna()
            if (
                request.warmup_sessions is not None
                and "bars_seen" in joined.columns
            ):
                bars = pd.to_numeric(
                    joined["bars_seen"], errors="coerce"
                )
                warmup = (
                    value_missing
                    & bars.lt(request.warmup_sessions)
                )
                reason.loc[warmup] = "WARMUP_INSUFFICIENT"
                value_missing &= ~warmup
            reason.loc[value_missing] = "FEATURE_VALUE_NULL"

            joined[
                f"__feature_availability__{col}"
            ] = request.status.value
            joined[
                f"__feature_missing_reason__{col}"
            ] = reason

            audit_rows.append(
                {
                    "column": col,
                    "kind": request.kind,
                    "required": request.required,
                    "availability_status": request.status.value,
                    "dependencies": ";".join(request.dependencies),
                    "panel_rows": len(joined),
                    "artifact_rows_present": int(present.sum()),
                    "value_nonnull": int(joined[col].notna().sum()),
                    "artifact_row_absent": int(
                        (reason == "ARTIFACT_ROW_ABSENT").sum()
                    ),
                    "warmup_insufficient": int(
                        (reason == "WARMUP_INSUFFICIENT").sum()
                    ),
                    "feature_value_null": int(
                        (reason == "FEATURE_VALUE_NULL").sum()
                    ),
                }
            )

        joined = joined.drop(columns=["__artifact_row_present"])
        audit = pd.DataFrame(audit_rows)

        period = manifest["period"]
        panel_start = pd.Timestamp(joined["date"].min()).normalize()
        panel_end = pd.Timestamp(joined["date"].max()).normalize()
        cutoff_contracts: list[str] = []
        if "available_at_date" in joined.columns:
            cutoff_contracts.append("available_at_date<=logical_date")
        if (
            "source_available_at" in joined.columns
            and "__decision_cutoff_at" in joined.columns
        ):
            cutoff_contracts.append("source_available_at<decision_cutoff_at")

        feature_rows = tuple(
            VerifiedFeatureEvidence(
                column=request.column,
                kind=request.kind,
                required=request.required,
                warmup_sessions=request.warmup_sessions,
                dependencies=request.dependencies,
                status=request.status,
            )
            for request in self.config.requested_features
        )
        base_payload = {
            "schema_version": "1",
            "scope": self.evidence_scope,
            "evidence_source": self.evidence_source,
            "integration_name": self.config.name,
            "integration_config_sha256": stable_object_sha256(self.config),
            "manifest_path": str(self.manifest_path.resolve()),
            "manifest_sha256": sha256_file(self.manifest_path),
            "artifact_name": str(manifest["artifact_name"]),
            "source_revision": str(manifest["source_revision"]),
            "formula_version": str(manifest["formula_version"]),
            "epoch": str(manifest["epoch"]),
            "manifest_period_start": str(pd.Timestamp(period[0]).date()),
            "manifest_period_end": str(pd.Timestamp(period[1]).date()),
            "panel_date_start": str(panel_start.date()),
            "panel_date_end": str(panel_end.date()),
            "cutoff_contracts": tuple(cutoff_contracts),
            "requested_features": feature_rows,
            "artifacts": artifact_evidence,
            "hydrated_panel_sha256": dataframe_sha256(joined),
            "audit_sha256": dataframe_sha256(audit),
        }
        evidence = FeaturePanelEligibilityEvidence(
            **base_payload,
            evidence_sha256=stable_object_sha256(base_payload),
        )
        return FeaturePanelJoinResult(
            frame=joined,
            audit=audit,
            manifest=manifest,
            evidence=evidence,
        )
