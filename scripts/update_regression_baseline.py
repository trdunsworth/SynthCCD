#!/usr/bin/env python3
"""Regenerate tests/regression_baseline.json after intentional realism changes.

The regression suite (tests/test_regression.py) compares freshly generated
signatures against this committed baseline. Run this script whenever realism
defaults are *intentionally* changed (weights, time profiles, phone metrics),
then review the printed delta and commit the new baseline together with the
code change.

Usage:
    uv run python scripts/update_regression_baseline.py [--seed N] [--output PATH]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from synth911gen3.regression import build_baseline, load_baseline, save_baseline

DEFAULT_BASELINE = Path(__file__).resolve().parent.parent / "tests" / "regression_baseline.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=None, help="Override baseline seed")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_BASELINE,
        help="Baseline file to write (default: tests/regression_baseline.json)",
    )
    args = parser.parse_args()

    kwargs = {}
    if args.seed is not None:
        kwargs["seed"] = args.seed

    baseline = build_baseline(**kwargs)

    if args.output.exists():
        previous = load_baseline(args.output)
        print("Changes vs existing baseline:")
        for section in ("incidents", "phone"):
            # Report every differing key so an intentional realism change is
            # visible before committing, not just out-of-tolerance drift.
            all_keys = sorted(set(baseline[section]) | set(previous[section]))
            printed = False
            for key in all_keys:
                old = previous[section].get(key)
                new = baseline[section].get(key)
                if old != new:
                    printed = True
                    print(f"  {key}: {old} -> {new}")
            if not printed:
                print(f"  ({section}: unchanged)")
    else:
        print(f"No existing baseline at {args.output}; creating a new one.")

    save_baseline(baseline, args.output)
    print(f"\nWrote {args.output}")
    print("Review `git diff -- tests/regression_baseline.json` before committing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
