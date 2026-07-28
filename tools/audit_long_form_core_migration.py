#!/usr/bin/env python3
"""Create a read-only audit of long-form migration from static core."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from yime.input_model.long_form_migration import (  # noqa: E402
    DEFAULT_POLICY_PATH,
    audit_long_form_core_migration,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "审计零证据、完全可恢复的普通长串是否已移出静态核心；"
            "不删除来源、不写候选裁决。"
        )
    )
    parser.add_argument(
        "--capacity-database",
        type=Path,
        default=(
            ROOT
            / ".generated"
            / "static_lexicon_capacity"
            / "static_capacity.sqlite3"
        ),
    )
    parser.add_argument(
        "--input-model-database",
        type=Path,
        default=(
            ROOT
            / ".generated"
            / "input_candidate_model"
            / "input_model.sqlite3"
        ),
    )
    parser.add_argument(
        "--selection",
        type=Path,
        default=(
            ROOT
            / ".generated"
            / "two_level_runtime_trial"
            / "selection.tsv"
        ),
    )
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    parser.add_argument(
        "--output",
        type=Path,
        default=(
            ROOT
            / ".generated"
            / "long_form_core_migration"
            / "report.json"
        ),
    )
    parser.add_argument("--sample-limit", type=int, default=100)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    audit = audit_long_form_core_migration(
        capacity_database=args.capacity_database,
        input_model_database=args.input_model_database,
        selection_path=args.selection,
        policy_path=args.policy,
        sample_limit=args.sample_limit,
    )
    payload = {
        "schema_version": 1,
        "tool": "audit_long_form_core_migration",
        "inputs": {
            "capacity_database": str(args.capacity_database.resolve()),
            "input_model_database": str(
                args.input_model_database.resolve()
            ),
            "selection": str(args.selection.resolve()),
            "policy": str(args.policy.resolve()),
        },
        "audit": asdict(audit),
        "decision": (
            "pass"
            if audit.selected_violations == 0
            else "fail_selected_runtime_contains_migration_candidates"
        ),
        "safeguards": {
            "source_mutation": False,
            "writes_assessments": False,
            "noise_label": False,
            "dynamic_recoverability_preserved": True,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"report: {args.output.resolve()}")
    print(f"eligible_texts: {audit.eligible_texts}")
    print(f"protected_texts: {audit.protected_texts}")
    print(f"selected_long_texts: {audit.selected_long_texts}")
    print(f"selected_violations: {audit.selected_violations}")
    print(f"decision: {payload['decision']}")
    return 0 if audit.selected_violations == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
