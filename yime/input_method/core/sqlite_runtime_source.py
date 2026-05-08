from __future__ import annotations

import sqlite3
from pathlib import Path


class SQLiteRuntimeSource:
    """Connection and metadata helper for SQLite runtime candidate sources."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        if not self.db_path.exists():
            raise FileNotFoundError(f"未找到输入法数据库: {self.db_path}")

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        return connection

    def validate_runtime_candidates_view(self) -> None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT type FROM sqlite_master WHERE name = 'runtime_candidates'"
            ).fetchone()
            if row is None:
                raise ValueError("数据库中缺少 runtime_candidates 视图")

    def detect_runtime_candidate_table(self) -> str:
        self.validate_runtime_candidates_view()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT type FROM sqlite_master WHERE name = 'runtime_candidates_materialized'"
            ).fetchone()
            if row is None:
                return "runtime_candidates"

            materialized_sample = conn.execute(
                "SELECT 1 FROM runtime_candidates_materialized LIMIT 1"
            ).fetchone()
            if materialized_sample is not None:
                return "runtime_candidates_materialized"
        return "runtime_candidates"
