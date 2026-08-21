from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from yime.input_method.utils.runtime_reverse_lookup import RuntimeReverseLookup
from yime.utils.prototype_runtime_parity import build_compact_parity_database


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _prepare_selected_source(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE prototype_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                note TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE runtime_lexicon_selection (
                entry_type TEXT NOT NULL,
                text TEXT NOT NULL,
                pinyin_tone TEXT NOT NULL,
                selection_level TEXT NOT NULL,
                selection_reason TEXT NOT NULL,
                source_full_layout_code TEXT NOT NULL,
                source_weight INTEGER NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (entry_type, text, pinyin_tone)
            );
            CREATE TABLE runtime_candidates_materialized (
                entry_type TEXT NOT NULL,
                entry_id TEXT NOT NULL,
                text TEXT NOT NULL,
                pinyin_tone TEXT NOT NULL,
                yime_code TEXT NOT NULL,
                full_yime_code TEXT NOT NULL,
                primary_yime_code TEXT NOT NULL,
                variable_yinyuan_code TEXT NOT NULL,
                input_shorthand_code TEXT NOT NULL,
                sort_weight REAL NOT NULL,
                is_common INTEGER NOT NULL,
                text_length INTEGER NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (entry_type, entry_id, pinyin_tone)
            );
            """
        )
        connection.executemany(
            "INSERT INTO prototype_metadata (key, value) VALUES (?, ?)",
            (
                ("runtime_lexicon_selection_active", "1"),
                ("runtime_lexicon_selection_sha256", "selection-sha"),
            ),
        )
        connection.executemany(
            """
            INSERT INTO runtime_lexicon_selection (
                entry_type, text, pinyin_tone, selection_level,
                selection_reason, source_full_layout_code, source_weight
            ) VALUES (?, ?, ?, 'first_level', 'fixture', ?, 10)
            """,
            (
                ("char", "甲", "jia3", "KEY-A"),
                ("char", "甲", "jia4", "KEY-A"),
                ("phrase", "甲乙", "jia3 yi3", "KEY-B"),
            ),
        )
        connection.executemany(
            """
            INSERT INTO runtime_candidates_materialized VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, 'fixture'
            )
            """,
            (
                ("char", "1", "甲", "jia3", "A", "A", "B", "B", "C", 10, 1),
                ("char", "2", "甲", "jia4", "A", "A", "B", "B", "C", 11, 1),
                (
                    "phrase",
                    "3",
                    "甲乙",
                    "jia3 yi3",
                    "DD",
                    "DD",
                    "EE",
                    "EE",
                    "FF",
                    9,
                    2,
                ),
            ),
        )


def test_compact_runtime_matches_windows_candidate_identity(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    output = tmp_path / "parity.db"
    dictionary_manifest = tmp_path / "dictionary.json"
    runtime_manifest = tmp_path / "runtime.json"
    output_manifest = tmp_path / "output.json"
    _prepare_selected_source(source)
    _write_json(
        dictionary_manifest,
        {
            "total_reading_entries": 2,
            "total_distinct_texts": 2,
            "selection_tsv_sha256": "selection-sha",
            "output_sha256": "dictionary-sha",
        },
    )
    _write_json(runtime_manifest, {"selection_tsv_sha256": "selection-sha"})

    payload = build_compact_parity_database(
        source_database=source,
        output_database=output,
        dictionary_manifest_path=dictionary_manifest,
        runtime_manifest_path=runtime_manifest,
        layout_digest="layout-digest",
        output_manifest_path=output_manifest,
    )

    assert payload["status"] == "passed"
    assert payload["entry_count"] == 2
    assert payload["distinct_texts"] == 2
    assert payload["source_materialized_rows"] == 3
    connection = sqlite3.connect(output)
    try:
        assert connection.execute(
            "SELECT text, pinyin_tone FROM runtime_candidates_materialized ORDER BY text"
        ).fetchall() == [("甲", "jia4"), ("甲乙", "jia3 yi3")]
    finally:
        connection.close()

    first_sha = payload["database_sha256"]
    rebuilt = build_compact_parity_database(
        source_database=source,
        output_database=output,
        dictionary_manifest_path=dictionary_manifest,
        runtime_manifest_path=runtime_manifest,
        layout_digest="layout-digest",
        output_manifest_path=output_manifest,
    )
    assert rebuilt["database_sha256"] == first_sha


def test_compact_runtime_reverse_lookup_uses_packaged_pinyin_map(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.db"
    output = tmp_path / "parity.db"
    dictionary_manifest = tmp_path / "dictionary.json"
    runtime_manifest = tmp_path / "runtime.json"
    output_manifest = tmp_path / "output.json"
    marked = tmp_path / "pinyin_normalized.json"
    _prepare_selected_source(source)
    _write_json(
        dictionary_manifest,
        {
            "total_reading_entries": 2,
            "total_distinct_texts": 2,
            "selection_tsv_sha256": "selection-sha",
            "output_sha256": "dictionary-sha",
        },
    )
    _write_json(runtime_manifest, {"selection_tsv_sha256": "selection-sha"})
    _write_json(marked, {"jia4": "jià", "yi3": "yǐ"})
    build_compact_parity_database(
        source_database=source,
        output_database=output,
        dictionary_manifest_path=dictionary_manifest,
        runtime_manifest_path=runtime_manifest,
        layout_digest="layout-digest",
        output_manifest_path=output_manifest,
    )

    lookup = RuntimeReverseLookup(
        output,
        user_db_path=tmp_path / "user.db",
        numeric_to_marked_path=marked,
    )
    record = lookup.lookup_first("甲")

    assert record is not None
    assert record.numeric_pinyin == "jia4"
    assert record.marked_pinyin == "jià"
    assert record.yime_code == "B"
