#!/usr/bin/env python3
"""Initialize the candidate decision overlay and seed its review queue."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from yime.input_model import build_input_model


DEFAULT_SOURCE = ROOT / ".generated" / "lexicon_source_bundle" / "source_lexicon.sqlite3"
DEFAULT_OUTPUT = ROOT / ".generated" / "input_candidate_model" / "input_model.sqlite3"
DEFAULT_POLICY = ROOT / "internal_data" / "input_candidate_model_policy.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the reviewable input-candidate decision overlay.",
    )
    parser.add_argument("--source-database", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-database", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--proposal-limit", type=int, default=10_000)
    parser.add_argument("--minimum-frequency", type=int, default=1)
    parser.add_argument(
        "--minimum-text-length",
        type=int,
        default=2,
        help="Default 2 keeps the initial review queue focused on multi-character materials.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.proposal_limit < 1:
        raise ValueError("proposal-limit must be positive")
    result = build_input_model(
        source_database=args.source_database,
        output_database=args.output_database,
        policy_path=args.policy,
        proposal_limit=args.proposal_limit,
        minimum_frequency=args.minimum_frequency,
        minimum_text_length=args.minimum_text_length,
    )
    print(f"input_model_database: {result.database}")
    print(f"proposals_added: {result.proposals_added}")
    print(f"proposals_preserved: {result.proposals_preserved}")
    print(f"status_counts: {result.status_counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
