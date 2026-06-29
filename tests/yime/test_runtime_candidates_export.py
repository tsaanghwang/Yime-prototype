from __future__ import annotations

import sqlite3

from yime.utils.runtime_candidates_export import normalize_sort_weight_for_export
from yime.utils.runtime_candidates_export import build_candidate_record, group_rows
from yime.utils.runtime_codes_refresh import rebuild_materialized_runtime_candidates


def test_normalize_sort_weight_for_export_rounds_binary_tail() -> None:
    assert normalize_sort_weight_for_export(3.7152000000000003) == 3.7152


def test_normalize_sort_weight_for_export_keeps_integer_weight_stable() -> None:
    assert normalize_sort_weight_for_export(120) == 120.0


def test_build_candidate_record_keeps_primary_yime_code() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """
        SELECT
            '啊' AS text,
            'char' AS entry_type,
            '1' AS entry_id,
            'a1' AS pinyin_tone,
            'ABCD' AS yime_code,
            'AB' AS primary_yime_code,
            1.0 AS sort_weight,
            1 AS is_common,
            1 AS text_length,
            '2026-06-25' AS updated_at
        """
    ).fetchone()

    record = build_candidate_record(row)

    assert record["yime_code"] == "ABCD"
    assert record["primary_yime_code"] == "AB"
    conn.close()


def test_group_rows_prefers_primary_yime_code() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """
        SELECT
            '啊' AS text,
            'char' AS entry_type,
            '1' AS entry_id,
            'a1' AS pinyin_tone,
            'ABCD' AS yime_code,
            'AB' AS primary_yime_code,
            1.0 AS sort_weight,
            1 AS is_common,
            1 AS text_length,
            '2026-06-25' AS updated_at
        """
    ).fetchone()

    grouped = group_rows([row], limit_per_code=0)

    assert list(grouped) == ["AB"]
    assert grouped["AB"][0]["yime_code"] == "ABCD"
    conn.close()


def test_materialized_runtime_candidates_store_primary_yime_code_and_match_export_grouping() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE runtime_candidates (
            entry_type TEXT NOT NULL,
            entry_id TEXT NOT NULL,
            text TEXT NOT NULL,
            pinyin_tone TEXT NOT NULL,
            yime_code TEXT NOT NULL,
            sort_weight REAL NOT NULL,
            is_common INTEGER NOT NULL,
            text_length INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE runtime_candidates_materialized (
            entry_type TEXT NOT NULL,
            entry_id TEXT NOT NULL,
            text TEXT NOT NULL,
            pinyin_tone TEXT NOT NULL,
            yime_code TEXT NOT NULL,
            sort_weight REAL NOT NULL,
            is_common INTEGER NOT NULL,
            text_length INTEGER NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (entry_type, entry_id)
        );
        """
    )
    conn.execute(
        """
        INSERT INTO runtime_candidates (
            entry_type,
            entry_id,
            text,
            pinyin_tone,
            yime_code,
            sort_weight,
            is_common,
            text_length,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("char", "1", "啊", "a1", "􀀋􀀩􀀩􀀩", 1.0, 1, 1, "2026-06-25"),
    )

    rebuilt_rows = rebuild_materialized_runtime_candidates(conn)
    materialized = conn.execute(
        """
        SELECT
            entry_type,
            entry_id,
            text,
            pinyin_tone,
            yime_code,
            primary_yime_code,
            sort_weight,
            is_common,
            text_length,
            updated_at
        FROM runtime_candidates_materialized
        """
    ).fetchall()
    grouped = group_rows(materialized, limit_per_code=0)

    assert rebuilt_rows == 1
    assert len(materialized) == 1
    assert materialized[0]["yime_code"] == "􀀋􀀩􀀩􀀩"
    assert materialized[0]["primary_yime_code"] == "􀀋􀀩"
    assert list(grouped) == ["􀀋􀀩"]
    conn.close()
