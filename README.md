# synth911gen3

TUI-first scaffold for generating synthetic 9-1-1 CAD incidents and hourly phone-center counts with `uv`.

## What is scaffolded

- `src\synth911gen3\` application package with shared generator services
- CAD incident generation with agency, priority, lifecycle timestamps, personnel, and elapsed seconds
- Hourly call-count generation for 9-1-1, non-emergency, abandoned, and outbound calls
- Export routing for CSV, Parquet, JSON, YAML, pandas, and polars
- OpenStreetMap-backed address provider abstraction
- Typer CLI and Textual TUI entrypoints
- Pytest coverage for defaults, generation flow, and export behavior

## Environment

```powershell
uv venv
uv sync
```

Activate the virtual environment in PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

## Run the generator

Generate the default datasets into `output\`:

```powershell
uv run synth911gen3 generate
```

Generate only incidents in parquet format:

```powershell
uv run synth911gen3 generate --dataset incidents --format parquet --rows 5000
```

Launch the TUI:

```powershell
uv run synth911gen3 tui
```

## Quality checks

```powershell
uv run pytest tests/
uv run ruff check .
uv run ty check
uv run scripts/audit_deps.py   # dependency security audit (pip-audit)
```

On networks behind a TLS-inspecting proxy, prefix the audit with
`$env:SYNTH911_SYSTEM_TRUST = "1"` so it verifies against the OS trust store.
