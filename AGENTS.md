# AGENTS.md

You are an experienced Python developer working on this project under my guidance.

## Task

The task is to build a synthetic data generator that emulates data that could be found inside dispatch archival records and in phone equipment.

## Tech Stack

- Framnework: Python, Faker, Numpy, SciPy
- Language: Python
- Package Manager: uv
- Validation: ruff
- Testing: pytest

## UV Package Manager

### Initial Setup

curl -LsSf <https://astral.sh/uv/install.sh> | sh
uv venv
source .venv/bin/activate  # Linux/Mac

### Dependency Management

- `uv sync` - Install from lock file
- `uv add boto3` - Add runtime dependency
- `uv add --group dev pytest` - Add dev dependency
- `uv add "fastapi>=0.110,<1"` - Add with version constraint
- `uv lock` - Update lock file
- `uv run <command>` - Run command in venv

### Important

- Commit `uv.lock` for reproducibility
- Use `uv sync` for consistent environments

## Environment Setup

- Python 3.12+
- Initialize project: `uv init synth911gen3`
- Create environment: `uv venv && source .venv/bin/activate`
- Install dependencies: `uv sync`
- Lock environment: `uv lock`

## Commands

- Install package: `uv add` + package name
- Run tests: `uv run pytest tests/*`
- Lint files: `uv run ruff check`
- Type hinting `uv run ty check`

## Code Style

- Python: Follow PEP 8 using ruff
- Formatting: Ruff
- Type Hinting: Ty
- Never hardcode any credentials

## Testing

- Framework: pytest
- Unit Tests: `uv run pytest tests/`
- Coverage requirement: 80%+ fpr new code

## Project Structure

- `src/` - Source material for review
- `docs/` - Documentation for instruction and output
- `output/` - Location of generated files
- `tests/` - testing plans go here.

## Permissions

### Allowed without prompting

- Read files
- Write tests
- List Directories
- Single file linting, type checking, formatting
- Unit tests on specifc files

### Require approval

- Package installation outside of base files (`uv add`)
- Git operations (`git push`, `git commit`)
- File deletion
- Running full build

### Not allowed

- Alter files in `src/` directory
- Delete project

## PR Requirements

- Title format: [component] Brief description
- Always run `uv run pytest && uv run ruff check .` before committing
- Keep diffs small and focused
- Tests required for new features
- All CI checks must pass
