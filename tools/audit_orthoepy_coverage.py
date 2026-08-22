#!/usr/bin/env python3
"""Audit and optionally export orthoepy-based candidate coverage additions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from yime.lexicon_bundle.orthoepy_coverage import (  # noqa: E402
    CoverageReviewStore,
    export_approved_catalog,
    run_coverage_audit,
)


DEFAULT_OUTPUT = ROOT / ".generated" / "orthoepy_coverage"
DEFAULT_PSC_DB = (
    ROOT / "external_data" / "psc_outline" / "psc_outline_ocr.sqlite3"
)
DEFAULT_SOURCE_DB = (
    ROOT / ".generated" / "lexicon_source_bundle" / "source_lexicon.sqlite3"
)
DEFAULT_CATALOG = (
    ROOT / "internal_data" / "pinyin_source_db" / "orthoepy_coverage_readings.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--psc-db", type=Path, default=DEFAULT_PSC_DB)
    parser.add_argument("--source-db", type=Path, default=DEFAULT_SOURCE_DB)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--decoder-inventory", type=Path, default=ROOT / "yime" / "pinyin_normalized.json"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Export automatic official additions and manually approved records to the reviewed source catalog.",
    )
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--decision-database", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    audit_database = args.output_dir / "orthoepy_coverage.sqlite3"
    result = run_coverage_audit(
        args.psc_db,
        args.source_db,
        audit_database,
        decoder_inventory=args.decoder_inventory,
    )
    if args.apply:
        store = CoverageReviewStore(audit_database, args.decision_database)
        try:
            result["catalog"] = export_approved_catalog(
                store, args.catalog, decoder_inventory=args.decoder_inventory
            )
        finally:
            store.close()
    summary = args.output_dir / "summary.json"
    summary.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
