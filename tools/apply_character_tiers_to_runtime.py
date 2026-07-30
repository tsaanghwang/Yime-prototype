#!/usr/bin/env python3
"""Copy unified nine-level character tiers into the runtime database."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from yime.lexicon_bundle.character_tiers import TIER_NAMES
from yime.utils.asset_paths import resolve_lexicon_source_db_path
from yime.utils.runtime_codes_refresh import (
    DB_PATH,
    rebuild_char_usage_profile,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Copy source_lexicon.sqlite3.character_tiers into "
            "pinyin_hanzi.db.char_usage_profile and refresh materialized "
            "single-character sort weights."
        )
    )
    parser.add_argument("--runtime-db", type=Path, default=DB_PATH)
    parser.add_argument(
        "--source-db",
        type=Path,
        default=resolve_lexicon_source_db_path(ROOT),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit changes; without this flag the transaction is rolled back.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    runtime_db = args.runtime_db.resolve()
    source_db = args.source_db.resolve()
    if not runtime_db.is_file():
        raise FileNotFoundError(f"runtime database not found: {runtime_db}")
    if not source_db.is_file():
        raise FileNotFoundError(f"unified source database not found: {source_db}")

    with sqlite3.connect(runtime_db) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            stats = rebuild_char_usage_profile(
                conn,
                source_db_path=source_db,
            )
            inventory_count = int(
                conn.execute("SELECT COUNT(*) FROM char_inventory").fetchone()[0]
            )
            profile_count = int(
                conn.execute("SELECT COUNT(*) FROM char_usage_profile").fetchone()[0]
            )
            if profile_count != inventory_count:
                raise RuntimeError(
                    "runtime tier coverage mismatch: "
                    f"inventory={inventory_count} profile={profile_count}"
                )

            conn.execute(
                """
                CREATE TEMP TABLE refreshed_char_weights (
                    entry_id TEXT PRIMARY KEY,
                    sort_weight REAL NOT NULL
                ) WITHOUT ROWID
                """
            )
            conn.execute(
                """
                INSERT INTO refreshed_char_weights (entry_id, sort_weight)
                SELECT entry_id, sort_weight
                FROM runtime_candidates
                WHERE entry_type = 'char'
                """
            )
            before = conn.total_changes
            conn.execute(
                """
                UPDATE runtime_candidates_materialized AS materialized
                SET sort_weight = (
                        SELECT refreshed.sort_weight
                        FROM refreshed_char_weights AS refreshed
                        WHERE refreshed.entry_id = materialized.entry_id
                    ),
                    updated_at = CURRENT_TIMESTAMP
                WHERE materialized.entry_type = 'char'
                  AND EXISTS (
                      SELECT 1
                      FROM refreshed_char_weights AS refreshed
                      WHERE refreshed.entry_id = materialized.entry_id
                  )
                """
            )
            materialized_updates = conn.total_changes - before
            tier_counts = Counter(
                {
                    tier_name: int(
                        conn.execute(
                            """
                            SELECT COUNT(*)
                            FROM char_usage_profile
                            WHERE usage_tier = ?
                            """,
                            (tier_name,),
                        ).fetchone()[0]
                    )
                    for tier_name in TIER_NAMES.values()
                }
            )

            if args.apply:
                conn.commit()
            else:
                conn.rollback()
        except Exception:
            conn.rollback()
            raise

    print(f"mode: {'applied' if args.apply else 'dry-run'}")
    print(f"runtime: {runtime_db}")
    print(f"source: {source_db}")
    print(f"profile_rows: {profile_count}")
    print(f"materialized_char_updates: {materialized_updates}")
    print(f"tier_step: {stats['tier_step']}")
    for tier_number, tier_name in TIER_NAMES.items():
        print(f"tier_{tier_number}_{tier_name}: {tier_counts[tier_name]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
