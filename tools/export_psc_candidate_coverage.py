#!/usr/bin/env python3
"""Export reviewed PSC pairs missing from the current runtime candidate set."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from yime.asset_paths import resolve_lexicon_source_db_path  # noqa: E402
from yime.lexicon_bundle.psc_candidate_coverage import (  # noqa: E402
    export_psc_candidate_catalog,
)


DEFAULT_AUDIT = (
    ROOT / ".generated" / "psc_pronunciation_audit" / "psc_pronunciation_audit.sqlite3"
)
DEFAULT_DECISIONS = (
    ROOT / ".generated" / "psc_pronunciation_audit" / "psc_transcription_review.sqlite3"
)
DEFAULT_OUTPUT = (
    ROOT / "internal_data" / "pinyin_source_db" / "psc_candidate_readings.json"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-database", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--decision-database", type=Path, default=DEFAULT_DECISIONS)
    parser.add_argument(
        "--source-database",
        type=Path,
        default=resolve_lexicon_source_db_path(ROOT),
    )
    parser.add_argument(
        "--decoder-inventory",
        type=Path,
        default=ROOT / "yime" / "pinyin_normalized.json",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    counts = export_psc_candidate_catalog(
        args.audit_database,
        args.decision_database,
        args.source_database,
        args.decoder_inventory,
        args.output,
    )
    print(json.dumps(counts, ensure_ascii=False, indent=2))
    print(f"output: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
