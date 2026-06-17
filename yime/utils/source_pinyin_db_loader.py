from __future__ import annotations

import sqlite3
from pathlib import Path


def uses_v2_source_schema(conn: sqlite3.Connection) -> bool:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(source_files)")}
    return "source_kind" in columns and "source_name" not in columns


def prototype_source_name(source_kind: str, source_path: str) -> str:
    return f"{source_kind}:{Path(source_path).name or source_path}"
