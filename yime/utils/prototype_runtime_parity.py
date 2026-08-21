"""Build and verify the compact prototype runtime matching Windows Yime."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from typing import Any
from contextlib import closing


RUNTIME_SCHEMA = """
CREATE TABLE prototype_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    note TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE runtime_candidates_materialized (
    entry_type TEXT NOT NULL,
    entry_id TEXT NOT NULL,
    text TEXT NOT NULL,
    pinyin_tone TEXT NOT NULL,
    yime_code TEXT NOT NULL,
    full_yime_code TEXT NOT NULL DEFAULT '',
    primary_yime_code TEXT NOT NULL DEFAULT '',
    variable_yinyuan_code TEXT NOT NULL DEFAULT '',
    input_shorthand_code TEXT NOT NULL DEFAULT '',
    sort_weight REAL NOT NULL,
    is_common INTEGER NOT NULL,
    text_length INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (entry_type, entry_id, pinyin_tone)
);
CREATE VIEW runtime_candidates AS
SELECT
    entry_type,
    entry_id,
    text,
    pinyin_tone,
    yime_code,
    sort_weight,
    is_common,
    text_length,
    updated_at
FROM runtime_candidates_materialized;
CREATE INDEX idx_runtime_candidates_materialized_primary_code
ON runtime_candidates_materialized(primary_yime_code, entry_type, sort_weight DESC, text);
CREATE INDEX idx_runtime_candidates_materialized_full_code
ON runtime_candidates_materialized(full_yime_code, entry_type, sort_weight DESC, text);
CREATE INDEX idx_runtime_candidates_materialized_variable_code
ON runtime_candidates_materialized(variable_yinyuan_code, entry_type, sort_weight DESC, text);
CREATE INDEX idx_runtime_candidates_materialized_shorthand_code
ON runtime_candidates_materialized(input_shorthand_code, entry_type, sort_weight DESC, text);
CREATE INDEX idx_runtime_candidates_materialized_text
ON runtime_candidates_materialized(text, sort_weight DESC, pinyin_tone);
"""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _require_equal(label: str, actual: object, expected: object) -> None:
    if actual != expected:
        raise ValueError(f"{label} mismatch: actual={actual!r}, expected={expected!r}")


def _source_selection_state(database: Path) -> dict[str, object]:
    with closing(
        sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    ) as connection:
        metadata = dict(
            connection.execute(
                """
                SELECT key, value
                FROM prototype_metadata
                WHERE key IN (
                    'runtime_lexicon_selection_active',
                    'runtime_lexicon_selection_sha256'
                )
                """
            ).fetchall()
        )
        selection_rows = int(
            connection.execute(
                "SELECT COUNT(*) FROM runtime_lexicon_selection"
            ).fetchone()[0]
        )
        materialized_rows = int(
            connection.execute(
                "SELECT COUNT(*) FROM runtime_candidates_materialized"
            ).fetchone()[0]
        )
    return {
        "active": str(metadata.get("runtime_lexicon_selection_active") or ""),
        "selection_sha256": str(
            metadata.get("runtime_lexicon_selection_sha256") or ""
        ),
        "selection_rows": selection_rows,
        "materialized_rows": materialized_rows,
    }


def build_compact_parity_database(
    *,
    source_database: Path,
    output_database: Path,
    dictionary_manifest_path: Path,
    runtime_manifest_path: Path,
    layout_digest: str,
    output_manifest_path: Path,
) -> dict[str, object]:
    dictionary_manifest = _read_json(dictionary_manifest_path)
    runtime_manifest = _read_json(runtime_manifest_path)
    expected_rows = int(dictionary_manifest["total_reading_entries"])
    expected_texts = int(dictionary_manifest["total_distinct_texts"])
    selection_sha = str(dictionary_manifest["selection_tsv_sha256"])
    _require_equal(
        "runtime selection SHA",
        str(runtime_manifest["selection_tsv_sha256"]),
        selection_sha,
    )

    source_state = _source_selection_state(source_database)
    if source_state["active"].strip().lower() not in {"1", "true", "yes", "on"}:
        raise ValueError("source runtime selection overlay is not active")
    _require_equal(
        "source runtime selection SHA",
        source_state["selection_sha256"],
        selection_sha,
    )

    output_database.parent.mkdir(parents=True, exist_ok=True)
    output_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = tempfile.NamedTemporaryFile(
        prefix=output_database.name + ".",
        suffix=".tmp",
        dir=output_database.parent,
        delete=False,
    )
    temporary_path = Path(temporary.name)
    temporary.close()
    temporary_path.unlink()

    connection = sqlite3.connect(temporary_path)
    try:
        connection.executescript(RUNTIME_SCHEMA)
        connection.execute("ATTACH DATABASE ? AS source", (str(source_database),))
        connection.execute(
            """
            INSERT INTO runtime_candidates_materialized (
                entry_type, entry_id, text, pinyin_tone, yime_code,
                full_yime_code, primary_yime_code, variable_yinyuan_code,
                input_shorthand_code, sort_weight, is_common, text_length,
                updated_at
            )
            SELECT
                entry_type, entry_id, text, pinyin_tone, yime_code,
                full_yime_code, primary_yime_code, variable_yinyuan_code,
                input_shorthand_code, sort_weight, is_common, text_length,
                updated_at
            FROM (
                SELECT
                    materialized.*,
                    ROW_NUMBER() OVER (
                        PARTITION BY
                            materialized.text,
                            selection.source_full_layout_code
                        ORDER BY
                            materialized.sort_weight DESC,
                            CASE materialized.entry_type
                                WHEN 'char' THEN 0 ELSE 1
                            END,
                            materialized.pinyin_tone,
                            materialized.entry_id
                    ) AS parity_rank
                FROM source.runtime_candidates_materialized AS materialized
                JOIN source.runtime_lexicon_selection AS selection
                  ON selection.entry_type = materialized.entry_type
                 AND selection.text = materialized.text
                 AND selection.pinyin_tone = materialized.pinyin_tone
            )
            WHERE parity_rank = 1
            ORDER BY text, pinyin_tone, entry_type, entry_id
            """
        )
        metadata_rows = [
            (
                "runtime_lexicon_selection_active",
                "1",
                "Windows-parity runtime selection is mandatory in this database.",
            ),
            (
                "runtime_lexicon_selection_sha256",
                selection_sha,
                "Two-level selection identity shared with Windows Yime.",
            ),
            (
                "prototype_runtime_profile",
                "windows_parity",
                "Compact evaluation runtime; full inventories remain offline.",
            ),
            (
                "prototype_runtime_source_dictionary_sha256",
                str(dictionary_manifest["output_sha256"]),
                "Source dictionary identity handed to Windows Yime.",
            ),
            (
                "prototype_runtime_layout_digest",
                layout_digest,
                "Canonical Yinyuan-to-key projection digest.",
            ),
        ]
        connection.executemany(
            """
            INSERT INTO prototype_metadata (key, value, note, updated_at)
            VALUES (?, ?, ?, '1970-01-01T00:00:00Z')
            """,
            metadata_rows,
        )
        connection.commit()
        connection.execute("DETACH DATABASE source")
        connection.execute("PRAGMA optimize")
        connection.commit()
    except Exception:
        connection.close()
        temporary_path.unlink(missing_ok=True)
        raise
    finally:
        if connection:
            connection.close()

    os.replace(temporary_path, output_database)
    payload = verify_compact_parity_database(
        database=output_database,
        dictionary_manifest_path=dictionary_manifest_path,
        expected_layout_digest=layout_digest,
        expected_selection_sha256=selection_sha,
    )
    payload.update(
        {
            "schema_version": "prototype-windows-parity-runtime-v1",
            "profile_id": "windows_parity",
            "source_database": str(source_database.resolve()),
            "source_materialized_rows": source_state["materialized_rows"],
            "dictionary_manifest": str(dictionary_manifest_path.resolve()),
            "runtime_manifest": str(runtime_manifest_path.resolve()),
            "source_dictionary_sha256": str(dictionary_manifest["output_sha256"]),
            "expected_entry_count": expected_rows,
            "expected_distinct_texts": expected_texts,
        }
    )
    output_manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def verify_compact_parity_database(
    *,
    database: Path,
    dictionary_manifest_path: Path,
    expected_layout_digest: str,
    expected_selection_sha256: str | None = None,
) -> dict[str, object]:
    dictionary_manifest = _read_json(dictionary_manifest_path)
    expected_rows = int(dictionary_manifest["total_reading_entries"])
    expected_texts = int(dictionary_manifest["total_distinct_texts"])
    expected_selection = expected_selection_sha256 or str(
        dictionary_manifest["selection_tsv_sha256"]
    )
    with closing(
        sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    ) as connection:
        actual_rows, actual_texts = connection.execute(
            """
            SELECT COUNT(*), COUNT(DISTINCT text)
            FROM runtime_candidates_materialized
            """
        ).fetchone()
        empty_mode_rows = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM runtime_candidates_materialized
                WHERE TRIM(full_yime_code) = ''
                   OR TRIM(variable_yinyuan_code) = ''
                   OR TRIM(input_shorthand_code) = ''
                """
            ).fetchone()[0]
        )
        metadata = dict(
            connection.execute(
                "SELECT key, value FROM prototype_metadata"
            ).fetchall()
        )
        integrity = str(connection.execute("PRAGMA quick_check").fetchone()[0])

    _require_equal("prototype runtime entry count", int(actual_rows), expected_rows)
    _require_equal("prototype runtime distinct texts", int(actual_texts), expected_texts)
    _require_equal("empty three-mode code rows", empty_mode_rows, 0)
    _require_equal("SQLite quick_check", integrity, "ok")
    _require_equal(
        "prototype runtime profile",
        metadata.get("prototype_runtime_profile"),
        "windows_parity",
    )
    _require_equal(
        "prototype runtime selection SHA",
        metadata.get("runtime_lexicon_selection_sha256"),
        expected_selection,
    )
    _require_equal(
        "prototype runtime layout digest",
        metadata.get("prototype_runtime_layout_digest"),
        expected_layout_digest,
    )
    _require_equal(
        "prototype runtime source dictionary SHA",
        metadata.get("prototype_runtime_source_dictionary_sha256"),
        str(dictionary_manifest["output_sha256"]),
    )
    return {
        "status": "passed",
        "database": str(database.resolve()),
        "database_bytes": database.stat().st_size,
        "database_sha256": sha256(database),
        "entry_count": int(actual_rows),
        "distinct_texts": int(actual_texts),
        "selection_tsv_sha256": expected_selection,
        "layout_digest": expected_layout_digest,
        "three_mode_codes_complete": True,
    }
