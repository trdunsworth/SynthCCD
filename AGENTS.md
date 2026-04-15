# AGENTS.md

You are an experienced Python developer working on this project under my guidance.

## Task

The task is to build a synthetic data generator that emulates data that could be found inside dispatch archival records and in phone equipment.

### Goals: 

Create software that can do the following:

1. Simulate CAD incident data that consists of:
   - Id number
   - Internal Reference number  
    - The internal reference number should be different by agency
   - Agency 
    - The minimum agency count must be 3: LAW, FIRE, and EMS
   - Problem Nature
   - Priority
   - Location 
    - address with directionals
    -  city
    - state* 
   - Datetime that the call starts
   - Times throughout the call life cycle
    - Call Start Time
    - Time Phone Pickup
    - Time Call Enters Queue
    - Time First Unit Assigned
    - Time Unit Enroute
    - Time Unit Arrived
    - Time Last Unit Cleared
    - Time Call Closed
   - Calltaker and Dispatcher
   - Method of Call Reception
    - 911
    - Phone
    - Radio
    - Walk In
    - Flag Down
  - Call Disposition
    -  Report Issued
    - No Report Issued
    - Cancelled
    - No Action Taken
   - Elapsed number of seconds between timestamps
2. Simulate hourly centre call counts of:
   - 9-1-1 calls received
   - 9-1-1 calls abandoned
   - non-emergency calls received
   - non-emergency calls abandoned
   - outbound calls placed
3. Ensure that all distributions, such as elapsed times between events, are realistic for priority and agency.
4. Export all datasets as csv, parquet, pandas dataframe, polar dataframe, JSON/YAML
5. Accessible through a TUI or a GUI depending on the users preference
6. Generate real addresses using data from [Open Street Map](https://www.openstreetmap.org/) 
7. Capapble of scaling to generate from hundreds to millions of rows of data at a time.
8. Allow the user to determine how many rows to generate, how it should be outputted, and what area to use for addresses with the following defaults: 10,000 rows in a csv file, and using Kansas City, MO as the default location.

You can examine the files in the source folder and use them as guidance. You may not alter any of these files. You may not use any names you find in these files for any dispatcher or calltaker names. You may use these files for calculations and distribution percentages to make the output data more realistic. You may not copy values over to the generated output.

You may also consult the .md files in the docs folder for recommendations that were generated from the previous version. They are suggestions and you may incorporate them if they prove valuable. You are also welcome to disregard any of them. 

Version 2 of this work, that you will replace, can be found at [https://github.com/trdunsworth/synth911gen2](https://github.com/trdunsworth/synth911gen2). You may consult the files in that repo to see how the previous version has been constructed.

Please place all tests in the tests file so I can review them later.

All outputted files should go into the output folder for now. That will change after a few iterations when we prepare for deployment

Check to see if uv is installed and updated before trying to install it.

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
- Coverage requirement: 80%+ for new code

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
