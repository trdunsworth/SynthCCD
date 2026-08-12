from __future__ import annotations

import hashlib
import json
import platform
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .config import GenerationRequest, OutputFormat
from .constants import DATA_SCHEMA_VERSION
from .realism_config import RealismConfig


MANIFEST_VERSION = "1.0"
PACKAGE_NAME = "synth911gen3"


@dataclass(slots=True)
class Manifest:
    version: str
    generated_at: str
    package: str
    package_version: str
    python_version: str
    platform: str
    seed: int
    rows_requested: int
    dataset: str
    output_format: str
    area_query: str
    start_date: str | None
    end_date: str | None
    id_format: str
    calltaker_pool_size: int
    dispatcher_pool_size: int
    shift_preset: str | None
    realism_config_hash: str | None
    max_memory_bytes: int | None
    schema_hash: str
    schema_version: str
    datasets_generated: list[str]
    row_counts: dict[str, int]
    column_counts: dict[str, int]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)

    def to_yaml(self) -> str:
        import yaml

        return yaml.safe_dump(asdict(self), sort_keys=False, default_flow_style=None)

    def to_kv_metadata(self) -> dict[str, str]:
        """Flatten this manifest to namespaced string key-value pairs.

        Used for Parquet footer metadata so generated files are
        self-documenting (seed, config hash, schema version, …). ``None``
        values are dropped; structured values (lists/dicts) are JSON-encoded.
        ``row_counts`` and ``column_counts`` are deliberately excluded because
        chunked export may not know final counts at write time — the sidecar
        manifest remains authoritative for those.
        """
        out: dict[str, str] = {}
        for key, value in asdict(self).items():
            if value is None or key in ("row_counts", "column_counts"):
                continue
            if isinstance(value, (dict, list)):
                value = json.dumps(value, sort_keys=True)
            out[f"synth911:{key}"] = str(value)
        return out

    @classmethod
    def from_request(
        cls,
        request: GenerationRequest,
        datasets: dict[str, pd.DataFrame] | None = None,
    ) -> Manifest:
        realism = request.get_realism_config()
        config_hash = _hash_realism_config(realism)
        schema_hash = _hash_schema(datasets) if datasets else ""

        return cls(
            version=MANIFEST_VERSION,
            generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            package=PACKAGE_NAME,
            package_version=_get_package_version(),
            python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            platform=platform.platform(),
            seed=request.seed,
            rows_requested=request.rows,
            dataset=request.dataset.value,
            output_format=request.output_format.value,
            area_query=request.area_query,
            start_date=request.start_date.isoformat() if request.start_date else None,
            end_date=request.end_date.isoformat() if request.end_date else None,
            id_format=request.id_format.value,
            calltaker_pool_size=request.calltaker_pool_size,
            dispatcher_pool_size=request.dispatcher_pool_size,
            shift_preset=request.shift_preset,
            realism_config_hash=config_hash,
            max_memory_bytes=request.max_memory_bytes,
            schema_hash=schema_hash,
            schema_version=DATA_SCHEMA_VERSION,
            datasets_generated=list(datasets.keys()) if datasets else [],
            row_counts={k: len(v) for k, v in datasets.items()} if datasets else {},
            column_counts={k: len(v.columns) for k, v in datasets.items()} if datasets else {},
        )


def _hash_realism_config(realism: RealismConfig) -> str:
    import yaml

    data = {
        "agency_weights": realism.agency_weights,
        "priority_weights": {k: v for k, v in realism.priority_weights.items()},
        "problem_profiles": {
            k: {str(pk): [[p, w] for p, w in pv] for pk, pv in v.items()}
            for k, v in realism.problem_profiles.items()
        },
        "call_reception_weights": realism.call_reception_weights,
        "disposition_profiles": {
            k: [[p, w] for p, w in v] for k, v in realism.disposition_profiles.items()
        },
        "time_profiles": {
            k: {str(pk): pv for pk, pv in v.items()} for k, v in realism.time_profiles.items()
        },
        "dispatch_init_fraction": {
            str(k): [lo, hi] for k, (lo, hi) in realism.dispatch_init_fraction.items()
        },
        "phone_metrics": realism.phone_metrics,
        "phone_metric_lines": realism.phone_metric_lines,
        "hourly_weights": realism.hourly_weights.tolist(),
        "agency_names": realism.agency_names,
        "shift_config": realism.shift_config.to_dict(),
        "seasonal_multipliers": realism.seasonal_multipliers,
        "name_locales": realism.name_locales,
    }
    yaml_str = yaml.safe_dump(data, sort_keys=True, default_flow_style=None)
    return hashlib.sha256(yaml_str.encode()).hexdigest()[:16]


def _hash_schema(datasets: dict[str, pd.DataFrame]) -> str:
    parts = []
    for name, frame in sorted(datasets.items()):
        cols = sorted(f"{c}:{frame[c].dtype}" for c in frame.columns)
        parts.append(f"{name}:{','.join(cols)}")
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def _get_package_version() -> str:
    try:
        from importlib.metadata import version

        return version(PACKAGE_NAME)
    except Exception:
        return "0.0.0-dev"


def write_manifest(
    manifest: Manifest,
    output_dir: Path,
    output_stem: str,
    output_format: OutputFormat,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{output_stem}_manifest.json"
    path.write_text(manifest.to_json(), encoding="utf-8")
    return path
