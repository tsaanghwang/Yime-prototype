"""Emit JSON metrics for lexicon trial integration (row counts + file checksums)."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sqlite_counts(db_path: Path) -> dict[str, int | str]:
    if not db_path.exists():
        return {"exists": False}

    conn = sqlite3.connect(db_path)
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        counts: dict[str, int | str] = {"exists": True}
        for table in (
            "char_readings",
            "phrase_readings",
            "single_char_readings",
            "runtime_candidates_materialized",
        ):
            if table in tables:
                counts[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        if "metadata" in tables:
            counts["metadata"] = dict(
                conn.execute("SELECT key, value FROM metadata ORDER BY key")
            )
        return counts
    finally:
        conn.close()


def file_metric(path: Path) -> dict[str, object]:
    return {
        "path": str(path),
        "exists": path.exists(),
        "bytes": path.stat().st_size if path.exists() else 0,
        "sha256": sha256_file(path),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect lexicon integration metrics.")
    parser.add_argument("--source-db", required=True)
    parser.add_argument("--runtime-db", default="")
    parser.add_argument("--baseline-runtime-db", default="")
    parser.add_argument("--runtime-json", default="")
    parser.add_argument("--encoding-json", default="")
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_db = Path(args.source_db)
    runtime_db = Path(args.runtime_db) if args.runtime_db else None
    baseline_runtime_db = (
        Path(args.baseline_runtime_db) if args.baseline_runtime_db else None
    )
    runtime_json = Path(args.runtime_json) if args.runtime_json else None
    encoding_json = Path(args.encoding_json) if args.encoding_json else None

    payload: dict[str, object] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_db": {
            **file_metric(source_db),
            "counts": sqlite_counts(source_db),
        },
    }
    if runtime_db is not None:
        payload["runtime_db"] = {
            **file_metric(runtime_db),
            "counts": sqlite_counts(runtime_db),
        }
    if baseline_runtime_db is not None:
        payload["baseline_runtime_db"] = {
            **file_metric(baseline_runtime_db),
            "counts": sqlite_counts(baseline_runtime_db),
        }
    if runtime_json is not None:
        payload["runtime_json"] = file_metric(runtime_json)
    if encoding_json is not None:
        payload["encoding_json"] = file_metric(encoding_json)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
