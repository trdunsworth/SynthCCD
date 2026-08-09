from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from synth911gen3.addresses import OpenStreetMapAddressProvider
from synth911gen3.app import Synth911Application
from synth911gen3.config import DatasetKind, GenerationRequest, IdFormat, OutputFormat
from synth911gen3.exceptions import AddressLookupError, ExportError, ValidationError
from synth911gen3.params import build_request_from_params, load_params_file

app = FastAPI(
    title="synth911gen3 API",
    description="Synthetic 911 CAD incident and hourly phone-center data generator",
    version="0.1.0",
)


class GenerationRequestModel(BaseModel):
    """Request model for data generation endpoint."""

    params_file: str | None = Field(
        default=None, description="Path to JSON/YAML/TOML params file (server-side)"
    )
    rows: int | None = Field(default=None, ge=1, description="Number of incident rows")
    area_query: str | None = Field(default=None, description="OpenStreetMap area query")
    output_format: str | None = Field(
        default=None, description="Output format: csv, parquet, json, yaml, pandas, polars"
    )
    dataset: str | None = Field(
        default=None, description="Dataset to generate: incidents, phone, all"
    )
    id_format: str | None = Field(default=None, description="ID format: integer or guid")
    output_dir: str | None = Field(default=None, description="Output directory")
    output_stem: str | None = Field(default=None, description="Filename stem for exports")
    start_date: str | None = Field(default=None, description="Start date YYYY-MM-DD")
    end_date: str | None = Field(default=None, description="End date YYYY-MM-DD")
    seed: int | None = Field(default=None, description="Random seed")
    calltaker_pool_size: int | None = Field(default=None, ge=1, description="Calltaker pool size")
    dispatcher_pool_size: int | None = Field(default=None, ge=1, description="Dispatcher pool size")
    shift_preset: str | None = Field(default=None, description="Shift preset name")
    max_memory_bytes: int | None = Field(default=None, ge=1, description="Per-chunk memory budget")
    realism_config_path: str | None = Field(default=None, description="Path to YAML realism config")

    @field_validator("output_format", mode="before")
    @classmethod
    def _validate_output_format(cls, v: str | None) -> str | None:
        if v is None:
            return None
        valid = {"csv", "parquet", "json", "yaml", "pandas", "polars"}
        if v.lower() not in valid:
            raise ValueError(f"output_format must be one of {valid}")
        return v.lower()

    @field_validator("dataset", mode="before")
    @classmethod
    def _validate_dataset(cls, v: str | None) -> str | None:
        if v is None:
            return None
        valid = {"incidents", "phone", "all"}
        if v.lower() not in valid:
            raise ValueError(f"dataset must be one of {valid}")
        return v.lower()

    @field_validator("id_format", mode="before")
    @classmethod
    def _validate_id_format(cls, v: str | None) -> str | None:
        if v is None:
            return None
        valid = {"integer", "guid"}
        if v.lower() not in valid:
            raise ValueError(f"id_format must be one of {valid}")
        return v.lower()


class SchemaResponse(BaseModel):
    """Schema information for a dataset."""

    dataset: str
    columns: list[dict[str, str]]
    row_count: int


class DryRunResponse(BaseModel):
    """Dry run response with schema and sample rows."""

    message: str
    schemas: list[SchemaResponse]


def _build_request(model: GenerationRequestModel) -> GenerationRequest:
    """Build GenerationRequest from API model."""
    cli_params: dict[str, Any] = {}
    if model.rows is not None:
        cli_params["rows"] = model.rows
    if model.area_query is not None:
        cli_params["area_query"] = model.area_query
    if model.output_format is not None:
        cli_params["output_format"] = OutputFormat(model.output_format.upper())
    if model.dataset is not None:
        cli_params["dataset"] = DatasetKind(model.dataset.upper())
    if model.id_format is not None:
        cli_params["id_format"] = IdFormat(model.id_format.upper())
    if model.output_dir is not None:
        cli_params["output_dir"] = Path(model.output_dir)
    if model.output_stem is not None:
        cli_params["output_stem"] = model.output_stem
    if model.start_date is not None:
        cli_params["start_date"] = model.start_date
    if model.end_date is not None:
        cli_params["end_date"] = model.end_date
    if model.seed is not None:
        cli_params["seed"] = model.seed
    if model.calltaker_pool_size is not None:
        cli_params["calltaker_pool_size"] = model.calltaker_pool_size
    if model.dispatcher_pool_size is not None:
        cli_params["dispatcher_pool_size"] = model.dispatcher_pool_size
    if model.shift_preset is not None:
        cli_params["shift_preset"] = model.shift_preset
    if model.max_memory_bytes is not None:
        cli_params["max_memory_bytes"] = model.max_memory_bytes
    if model.realism_config_path is not None:
        cli_params["realism_config_path"] = Path(model.realism_config_path)

    file_params = (
        load_params_file(Path(model.params_file)) if model.params_file else {}
    )
    return build_request_from_params(file_params, cli_params)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "service": "synth911gen3"}


@app.get("/schema")
async def get_schema(
    rows: int = Query(100, ge=1, description="Number of rows for schema probe"),
    dataset: str = Query("all", description="Dataset: incidents, phone, all"),
    output_format: str = Query("pandas", description="Output format for probe"),
    area_query: str = Query("Kansas City, MO", description="Area query for addresses"),
    seed: int = Query(911, description="Random seed"),
    config: str | None = Query(None, description="Path to realism config YAML"),
) -> DryRunResponse:
    """
    Get the schema (column names and types) for the generated datasets without
    fetching addresses or running a full generation. Uses a static address pool.
    """
    try:
        request = GenerationRequest(
            rows=rows,
            dataset=DatasetKind(dataset.upper()),
            output_format=OutputFormat(output_format.upper()),
            area_query=area_query,
            seed=seed,
            output_dir=Path("/tmp"),
            output_stem="schema_probe",
        )
        if config:
            request.realism_config_path = Path(config)

        from synth911gen3.describe import build_preview_datasets

        preview = build_preview_datasets(request, schema_only=True)

        schemas = []
        for name, frame in preview.items():
            schemas.append(
                SchemaResponse(
                    dataset=name,
                    columns=[
                        {"name": col, "type": str(dtype)}
                        for col, dtype in frame.dtypes.items()
                    ],
                    row_count=len(frame),
                )
            )

        return DryRunResponse(
            message="Schema preview: no files written, no OpenStreetMap fetch (illustrative sample addresses).",
            schemas=schemas,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/generate", response_model=None)
async def generate_data(
    request_model: GenerationRequestModel,
    download: bool = Query(
        False, description="If true, return file download; otherwise return JSON summary"
    ),
) -> Any:
    """
    Generate synthetic 911 data. Returns either a JSON summary of generated files
    or the file itself (for single-file formats like json/yaml).
    """
    try:
        request = _build_request(request_model)

        with TemporaryDirectory() as tmpdir:
            request.output_dir = Path(tmpdir)
            result = Synth911Application(
                address_provider=OpenStreetMapAddressProvider()
            ).generate(request)

            if request.output_format in (OutputFormat.PANDAS, OutputFormat.POLARS):
                return {
                    "message": "In-memory format requested; no files written.",
                    "incidents_shape": result.incidents.shape if result.incidents is not None else None,
                    "hourly_call_counts_shape": result.hourly_call_counts.shape if result.hourly_call_counts is not None else None,
                }

            # For file-based formats, return the first artifact or all artifacts
            artifacts = result.exported_artifacts
            if not artifacts:
                return {"message": "No artifacts generated"}

            if download and len(artifacts) == 1:
                # Single file download
                dataset_name, path = next(iter(artifacts.items()))
                return FileResponse(
                    path=path,
                    filename=Path(path).name,
                    media_type="application/octet-stream",
                )

            # Return summary of all generated files
            return {
                "message": "Generation complete",
                "files": {name: str(path) for name, path in artifacts.items()},
                "incidents_shape": result.incidents.shape if result.incidents is not None else None,
                "hourly_call_counts_shape": result.hourly_call_counts.shape if result.hourly_call_counts is not None else None,
            }

    except (AddressLookupError, ExportError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Internal error: {exc}")


@app.post("/generate/stream")
async def generate_data_stream(
    request_model: GenerationRequestModel,
    dataset: str = Query("incidents", description="Dataset to stream: incidents or phone"),
) -> StreamingResponse:
    """
    Stream generated data as CSV or Parquet. For large datasets, this avoids
    loading the entire file into memory.
    """
    try:
        request = _build_request(request_model)

        with TemporaryDirectory() as tmpdir:
            request.output_dir = Path(tmpdir)
            request.dataset = DatasetKind(dataset.upper())

            result = Synth911Application(
                address_provider=OpenStreetMapAddressProvider()
            ).generate(request)

            artifacts = result.exported_artifacts
            if not artifacts:
                raise HTTPException(status_code=404, detail="No data generated")

            dataset_key = f"{dataset}s" if dataset == "phone" else dataset
            if dataset_key not in artifacts:
                # Try exact match
                if dataset not in artifacts:
                    raise HTTPException(status_code=404, detail=f"Dataset {dataset} not found")
                dataset_key = dataset

            path = artifacts[dataset_key]
            suffix = Path(path).suffix.lower()

            if suffix == ".csv":
                media_type = "text/csv"
            elif suffix == ".parquet":
                media_type = "application/octet-stream"
            else:
                media_type = "application/octet-stream"

            def iter_file():
                with open(path, "rb") as f:
                    yield from f

            return StreamingResponse(
                iter_file(),
                media_type=media_type,
                headers={"Content-Disposition": f'attachment; filename="{Path(path).name}"'},
            )

    except (AddressLookupError, ExportError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Internal error: {exc}")


def run() -> None:
    """Entry point for the serve command."""
    import uvicorn

    uvicorn.run(
        "synth911gen3.serve:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    run()