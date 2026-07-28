#!/usr/bin/env python3
"""Validate or apply version-controlled lexicon review decisions."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from yime.input_model.decision_catalog import (
    apply_decision_catalog,
    load_decision_catalog,
    plan_decision_catalog,
)


DEFAULT_CATALOG = ROOT / "internal_data" / "lexicon_review_decisions.json"
DEFAULT_DATABASE = (
    ROOT / ".generated" / "input_candidate_model" / "input_model.sqlite3"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the committed lexicon decision catalog and show the exact "
            "overlay changes. No database writes occur unless --apply is supplied."
        )
    )
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write validated decisions to the generated input-model overlay",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="allow --apply to replace conflicting existing assessments",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.overwrite and not args.apply:
        raise SystemExit("--overwrite requires --apply")
    decisions = load_decision_catalog(args.catalog)
    plan = (
        apply_decision_catalog(
            args.database,
            decisions,
            overwrite=args.overwrite,
        )
        if args.apply
        else plan_decision_catalog(args.database, decisions)
    )
    print(f"mode: {'apply' if args.apply else 'dry-run'}")
    print(f"catalog: {args.catalog.resolve()}")
    print(f"database: {args.database.resolve()}")
    print(f"decisions: {len(decisions)}")
    print(f"created: {plan.created}")
    print(f"updated: {plan.updated}")
    print(f"unchanged: {plan.unchanged}")
    print(f"frequency_drift: {len(plan.frequency_drift)}")
    for text in plan.frequency_drift:
        print(f"frequency_drift_text: {text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
