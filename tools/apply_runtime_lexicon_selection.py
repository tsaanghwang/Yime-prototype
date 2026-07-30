"""Create or update a filtered experimental Yime runtime database."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from yime.utils.runtime_lexicon_selection import (
    apply_runtime_selection,
    clone_database,
    disable_runtime_selection,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-db", type=Path)
    parser.add_argument("--output-db", type=Path, required=True)
    parser.add_argument("--selection", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument(
        "--disable",
        action="store_true",
        help="Disable an existing selection overlay and rematerialize all.",
    )
    parser.add_argument(
        "--allow-unmatched",
        action="store_true",
        help="Keep going when selected dictionary rows have no runtime row.",
    )
    args = parser.parse_args()

    if args.source_db:
        clone_database(args.source_db, args.output_db)
    if args.disable:
        rows = disable_runtime_selection(args.output_db)
        print(json.dumps({"materialized_runtime_rows": rows}))
        return 0
    if args.selection is None:
        parser.error("--selection is required unless --disable is used")
    payload = apply_runtime_selection(
        args.output_db,
        args.selection,
        manifest_path=args.manifest,
        strict_unmatched=not args.allow_unmatched,
    )
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
