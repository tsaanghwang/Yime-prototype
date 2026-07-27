#!/usr/bin/env python3
"""Rebuild the nine-level character classification in source_lexicon.sqlite3."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from yime.lexicon_bundle.builder import default_inputs
from yime.lexicon_bundle.character_tiers import (
    export_character_tiers,
    rebuild_character_tiers,
)
from yime.utils.asset_paths import resolve_lexicon_source_db_path


def parse_args() -> argparse.Namespace:
    defaults = default_inputs()
    assert defaults.character_tier_sources is not None
    parser = argparse.ArgumentParser(
        description=(
            "Rebuild the mutually exclusive nine-level character tiers in the "
            "unified source database."
        )
    )
    parser.add_argument(
        "--source-db",
        type=Path,
        default=resolve_lexicon_source_db_path(ROOT),
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="TSV output; defaults beside source_lexicon.sqlite3.",
    )
    return parser.parse_args()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _update_manifest(
    path: Path,
    *,
    counts: dict[str, int],
    row_count: int,
    source_paths: tuple[Path, ...],
) -> None:
    if not path.is_file():
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["schema_version"] = "yime-gated-source-lexicon-v5"
    payload.setdefault("policy", {})["character_tiers"] = (
        "Nine mutually exclusive tiers are generated once in the unified "
        "source DB; runtime consumers copy encoded members without recomputing."
    )
    payload.setdefault("counts", {})["character_tier_rows"] = row_count
    payload["counts"]["character_tiers"] = counts
    payload.setdefault("outputs", {})["character_tiers"] = "character_tiers.tsv"

    sources = payload.setdefault("sources", [])
    by_path = {str(item.get("path", "")): item for item in sources}
    for source_path in source_paths:
        resolved = source_path.resolve()
        record = {
            "path": str(resolved),
            "sha256": _sha256(resolved),
            "bytes": resolved.stat().st_size,
        }
        existing = by_path.get(str(resolved))
        if existing is None:
            sources.append(record)
        else:
            existing.update(record)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    source_db = args.source_db.resolve()
    if not source_db.is_file():
        raise FileNotFoundError(f"unified source database not found: {source_db}")
    defaults = default_inputs()
    assert defaults.character_tier_sources is not None
    output = (
        args.output.resolve()
        if args.output is not None
        else source_db.parent / "character_tiers.tsv"
    )
    with sqlite3.connect(source_db) as conn:
        counts = rebuild_character_tiers(
            conn,
            defaults.character_tier_sources,
        )
        row_count = export_character_tiers(conn, output)
        conn.execute(
            """
            INSERT OR REPLACE INTO metadata (key, value)
            VALUES ('schema_version', 'yime-gated-source-lexicon-v5')
            """
        )
        conn.commit()
    _update_manifest(
        source_db.parent / "manifest.json",
        counts=counts,
        row_count=row_count,
        source_paths=defaults.character_tier_sources.paths(),
    )
    print(json.dumps(counts, ensure_ascii=False, indent=2))
    print(f"rows: {row_count}")
    print(f"database: {source_db}")
    print(f"tsv: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
