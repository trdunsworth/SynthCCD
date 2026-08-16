"""Build the Sphinx HTML documentation site.

Renders ``docsrc/`` (conf.py + reStructuredText sources) into
``output/docs/`` using the project's venv. Run from the repo root:

    uv run python scripts/build_docs.py [--clean] [--strict]

- ``--clean``  removes ``output/docs/`` before building.
- ``--strict`` treats Sphinx warnings as errors (useful in CI).

Exit status is the Sphinx build status (0 on success).
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCSRC = ROOT / "docsrc"
OUTPUT = ROOT / "output" / "docs"


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and invoke Sphinx, returning its exit status."""
    parser = argparse.ArgumentParser(description="Build the synth911gen3 documentation site.")
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove the output directory before building.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat Sphinx warnings as errors.",
    )
    args = parser.parse_args(argv)

    if args.clean and OUTPUT.exists():
        shutil.rmtree(OUTPUT)
        print(f"Removed {OUTPUT}")

    from sphinx.cmd.build import build_main

    cmd = ["-b", "html", "-E", "-j", "auto", str(DOCSRC), str(OUTPUT)]
    if args.strict:
        cmd.insert(0, "-W")
    status = build_main(cmd)

    if status == 0:
        print(f"\nDocumentation built: {OUTPUT}/index.html")
    else:
        print(f"\nSphinx exited with status {status}", file=sys.stderr)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
