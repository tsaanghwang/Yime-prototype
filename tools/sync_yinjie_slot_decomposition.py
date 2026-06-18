"""Rebuild ``yinjie_slot_decomposition`` from ``pinyin_yime_code``."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from yime.utils.yinjie_slot_decomposition import sync_yinjie_slot_decomposition

DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "yime" / "pinyin_hanzi.db"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    args = parser.parse_args()
    db_path = args.db.resolve()
    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")

    conn = sqlite3.connect(db_path)
    try:
        count = sync_yinjie_slot_decomposition(conn)
        conn.commit()
    finally:
        conn.close()

    print(f"Synced {count} rows into yinjie_slot_decomposition ({db_path})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
