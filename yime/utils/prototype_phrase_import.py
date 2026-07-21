from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import cast

from yime.asset_paths import resolve_lexicon_source_db_path
from yime.canonical_yime_mapping import load_canonical_code_map, sync_canonical_mapping_table
from yime.utils.char_frequency_policy import PHRASE_LEXICON_DEFAULT_FREQUENCY
from yime.utils.source_pinyin_db_loader import (
    prototype_source_name,
    uses_lexicon_bundle_schema,
    uses_v2_source_schema,
)


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = Path(__file__).resolve().parents[1] / "pinyin_hanzi.db"
SOURCE_DB_PATH = resolve_lexicon_source_db_path(WORKSPACE_ROOT)
SCHEMA_PATH = Path(__file__).resolve().parents[1] / "create_prototype_schema_additions.sql"

PREFERRED_PHRASE_READINGS: dict[str, tuple[str, str]] = {
    "朝阳": ("zhao1 yang2", "source-first ambiguous reading"),
    "那些": ("na4 xie1", "source-first ambiguous reading"),
}


def apply_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


def load_source_phrase_rows(path: Path) -> tuple[list[tuple[str, str, str]], list[tuple[int, str, str, str, str, int, str | None, str]]]:
    with sqlite3.connect(path) as source_conn:
        source_cur = source_conn.cursor()
        if uses_v2_source_schema(source_conn):
            source_file_rows = cast(
                list[tuple[str, str]],
                source_cur.execute(
                    '''
                    SELECT source_kind, source_path
                    FROM source_files
                    WHERE source_kind = 'phrase'
                    ORDER BY source_kind
                    '''
                ).fetchall(),
            )
            source_files = [
                (prototype_source_name(source_kind, source_path), source_kind, source_path)
                for source_kind, source_path in source_file_rows
            ]
            default_source_name = source_files[0][0] if source_files else "phrase:phrase_pinyin.txt"
            phrase_rows = cast(
                list[tuple[int, str, str, str, int]],
                source_cur.execute(
                    '''
                    SELECT id, phrase, marked_pinyin, numeric_pinyin, reading_rank
                    FROM phrase_readings
                    ORDER BY id
                    '''
                ).fetchall(),
            )
            rows: list[tuple[int, str, str, str, str, int, str | None, str]] = [
                (
                    row_id,
                    default_source_name,
                    phrase,
                    marked_pinyin,
                    numeric_pinyin,
                    reading_rank,
                    None,
                    "",
                )
                for row_id, phrase, marked_pinyin, numeric_pinyin, reading_rank in phrase_rows
            ]
            return source_files, rows

        source_files = cast(
            list[tuple[str, str, str]],
            source_cur.execute(
                '''
                SELECT source_name, source_kind, source_path
                FROM source_files
                WHERE source_kind = 'phrase'
                ORDER BY source_name
                '''
            ).fetchall(),
        )
        rows = cast(
            list[tuple[int, str, str, str, str, int, str | None, str]],
            source_cur.execute(
                '''
                SELECT id, source_name, phrase, marked_pinyin, numeric_pinyin,
                       reading_rank, comment, raw_line
                FROM phrase_readings
                ORDER BY id
                '''
            ).fetchall(),
        )
    return source_files, rows


def parse_numeric_pinyin_parts(pinyin_tone: str) -> tuple[str | None, str | None, int]:
    tone_number = int(pinyin_tone[-1]) if pinyin_tone and pinyin_tone[-1].isdigit() else 5
    final = pinyin_tone[:-1] if pinyin_tone and pinyin_tone[-1].isdigit() else pinyin_tone
    return None, final or None, tone_number


def parse_phrase_frequency(raw_line: str) -> int | None:
    payload = raw_line.split("#", 1)[0].strip()
    if not payload or ":" in payload:
        return None

    parts = [part.strip() for part in payload.split("\t")]
    if len(parts) < 3:
        return None

    try:
        return int(parts[2])
    except ValueError:
        return None


def build_phrase_yime_code(phrase_pinyin: str, yime_by_pinyin: dict[str, str]) -> str | None:
    syllable_codes: list[str] = []
    for syllable in phrase_pinyin.split():
        yime_code = yime_by_pinyin.get(syllable)
        if yime_code is None:
            return None

        syllable_codes.append(yime_code)

    return "".join(syllable_codes)


def sync_source_phrase_table(
    conn: sqlite3.Connection,
    source_files: list[tuple[str, str, str]],
    source_rows: list[tuple[int, str, str, str, str, int, str | None, str]],
) -> int:
    conn.execute("DELETE FROM phrase_readings")
    conn.execute("DELETE FROM source_files WHERE source_kind = 'phrase'")
    conn.executemany(
        '''
        INSERT INTO source_files (source_name, source_kind, source_path)
        VALUES (?, ?, ?)
        ''',
        source_files,
    )
    conn.executemany(
        '''
        INSERT INTO phrase_readings (
            id, source_name, phrase, marked_pinyin, numeric_pinyin,
            reading_rank, comment, raw_line
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        source_rows,
    )
    return len(source_rows)


def import_phrases_and_mappings(
    conn: sqlite3.Connection,
    source_rows: list[tuple[int, str, str, str, str, int, str | None, str]],
) -> tuple[int, int]:
    numeric_pinyin_rows = conn.execute('SELECT id, pinyin_tone FROM numeric_pinyin_inventory').fetchall()
    numeric_pinyin_by_text = {row[1]: row[0] for row in numeric_pinyin_rows}

    sync_canonical_mapping_table(conn, WORKSPACE_ROOT)
    yime_by_pinyin = load_canonical_code_map(WORKSPACE_ROOT)

    missing_numeric_rows: list[tuple[str, str | None, str | None, int, int | None, int | None]] = []
    seen_missing_numeric: set[str] = set()
    phrase_rows_by_text: dict[str, tuple[str, str | None, int | None, int, int, int | None]] = {}
    phrase_map_rows: list[tuple[int, str, int, str, str]] = []

    for _, source_name, phrase, _, numeric_pinyin, reading_rank, comment, raw_line in source_rows:
        for syllable in numeric_pinyin.split():
            if syllable in numeric_pinyin_by_text or syllable in seen_missing_numeric:
                continue
            initial, final, tone_number = parse_numeric_pinyin_parts(syllable)
            missing_numeric_rows.append((syllable, initial, final, tone_number, None, None))
            seen_missing_numeric.add(syllable)
        phrase_frequency = parse_phrase_frequency(raw_line)
        if phrase_frequency is None:
            phrase_frequency = PHRASE_LEXICON_DEFAULT_FREQUENCY
        if phrase not in phrase_rows_by_text:
            primary_yime_code = build_phrase_yime_code(numeric_pinyin, yime_by_pinyin)
            stored_phrase_code = primary_yime_code or numeric_pinyin
            phrase_rows_by_text[phrase] = (
                phrase,
                stored_phrase_code,
                phrase_frequency,
                len(phrase),
                1,
                None,
            )
            continue

        existing_phrase, stored_phrase_code, existing_frequency, phrase_length, is_common_phrase, legacy_phrase_id = phrase_rows_by_text[phrase]
        if existing_frequency is None:
            existing_frequency = PHRASE_LEXICON_DEFAULT_FREQUENCY
        if phrase_frequency > existing_frequency:
            phrase_rows_by_text[phrase] = (
                existing_phrase,
                stored_phrase_code,
                phrase_frequency,
                phrase_length,
                is_common_phrase,
                legacy_phrase_id,
            )

    if missing_numeric_rows:
        conn.executemany(
            '''
            INSERT OR IGNORE INTO numeric_pinyin_inventory (
                pinyin_tone,
                initial,
                final,
                tone_number,
                mapping_id,
                legacy_numeric_pinyin_id,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''',
            missing_numeric_rows,
        )
        numeric_pinyin_rows = conn.execute(
            'SELECT id, pinyin_tone FROM numeric_pinyin_inventory'
        ).fetchall()
        numeric_pinyin_by_text = {row[1]: row[0] for row in numeric_pinyin_rows}

    phrase_rows = list(phrase_rows_by_text.values())

    conn.execute('DELETE FROM phrase_inventory')
    conn.executemany(
        '''
        INSERT INTO phrase_inventory (
            phrase,
            yime_code,
            phrase_frequency,
            phrase_length,
            is_common_phrase,
            legacy_phrase_id,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''',
        phrase_rows,
    )

    phrase_id_by_text = {
        row[1]: row[0]
        for row in conn.execute('SELECT id, phrase FROM phrase_inventory')
    }

    conn.execute('DELETE FROM phrase_reading_preference')
    preferred_rows = [
        (phrase, preferred_pinyin_tone, reason)
        for phrase, (preferred_pinyin_tone, reason) in PREFERRED_PHRASE_READINGS.items()
        if phrase in phrase_id_by_text
    ]
    if preferred_rows:
        conn.executemany(
            '''
            INSERT INTO phrase_reading_preference (
                phrase,
                preferred_pinyin_tone,
                selection_reason,
                updated_at
            ) VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ''',
            preferred_rows,
        )

    conn.execute('DELETE FROM phrase_pinyin_map')

    for _, source_name, phrase, _, numeric_pinyin, reading_rank, comment, _ in source_rows:
        phrase_id = phrase_id_by_text[phrase]
        phrase_map_rows.append((
            phrase_id,
            numeric_pinyin,
            reading_rank,
            source_name,
            comment or 'source_pinyin.db.phrase_readings',
        ))

    conn.executemany(
        '''
        INSERT OR REPLACE INTO phrase_pinyin_map (phrase_id, pinyin_tone, reading_rank, source_file, source_note)
        VALUES (?, ?, ?, ?, ?)
        ''',
        phrase_map_rows,
    )

    return len(phrase_rows), len(phrase_map_rows)


def import_bundle_phrases_and_mappings(
    conn: sqlite3.Connection,
    source_path: Path,
    *,
    batch_size: int = 10_000,
) -> tuple[int, int, int]:
    """Stream primary phrase readings from the unified source without loading 2M rows."""
    source_name = "phrase:source_lexicon.sqlite3"
    conn.execute("DELETE FROM phrase_pinyin_map")
    conn.execute("DELETE FROM phrase_inventory")
    conn.execute("DELETE FROM phrase_reading_preference")
    conn.execute("DELETE FROM phrase_readings")
    conn.execute("DELETE FROM source_files WHERE source_kind = 'phrase'")
    conn.execute(
        "INSERT INTO source_files (source_name, source_kind, source_path) VALUES (?, 'phrase', ?)",
        (source_name, str(source_path)),
    )

    sync_canonical_mapping_table(conn, WORKSPACE_ROOT)
    yime_by_pinyin = load_canonical_code_map(WORKSPACE_ROOT)
    known_numeric = {
        str(row[0]) for row in conn.execute("SELECT pinyin_tone FROM numeric_pinyin_inventory")
    }
    phrase_count = phrase_map_count = missing_numeric_count = 0

    with sqlite3.connect(source_path) as source_conn:
        source_cursor = source_conn.execute(
            """
            SELECT id, text, marked_pinyin, numeric_pinyin, reading_rank,
                   bcc_frequency, pinyin_sources, reading_source_categories,
                   wanxiang_categories
            FROM canonical_readings
            WHERE text_length > 1 AND is_primary = 1
            ORDER BY id
            """
        )
        while batch := source_cursor.fetchmany(batch_size):
            phrase_inventory_rows: list[tuple[object, ...]] = []
            source_reading_rows: list[tuple[object, ...]] = []
            phrase_map_rows: list[tuple[object, ...]] = []
            missing_numeric_rows: list[tuple[object, ...]] = []

            for (
                row_id,
                phrase,
                marked_pinyin,
                numeric_pinyin,
                reading_rank,
                bcc_frequency,
                pinyin_sources,
                source_categories,
                wanxiang_categories,
            ) in batch:
                numeric_pinyin = str(numeric_pinyin)
                yime_code = build_phrase_yime_code(numeric_pinyin, yime_by_pinyin)
                if yime_code is None:
                    raise RuntimeError(
                        f"unified source passed its decoder gate but has no canonical code: "
                        f"{phrase} -> {numeric_pinyin}"
                    )
                for syllable in numeric_pinyin.split():
                    if syllable in known_numeric:
                        continue
                    initial, final, tone_number = parse_numeric_pinyin_parts(syllable)
                    missing_numeric_rows.append(
                        (syllable, initial, final, tone_number, None, None)
                    )
                    known_numeric.add(syllable)
                    missing_numeric_count += 1

                source_note = (
                    f"sources={pinyin_sources};categories={source_categories};"
                    f"wanxiang={wanxiang_categories}"
                )
                phrase_inventory_rows.append(
                    (
                        int(row_id),
                        str(phrase),
                        yime_code,
                        int(bcc_frequency),
                        len(str(phrase)),
                        1,
                        None,
                    )
                )
                source_reading_rows.append(
                    (
                        int(row_id),
                        source_name,
                        str(phrase),
                        str(marked_pinyin),
                        numeric_pinyin,
                        int(reading_rank),
                        source_note,
                        f"{phrase}\t{marked_pinyin}\t{int(bcc_frequency)}",
                    )
                )
                phrase_map_rows.append(
                    (
                        int(row_id),
                        numeric_pinyin,
                        int(reading_rank),
                        source_name,
                        source_note,
                    )
                )

            if missing_numeric_rows:
                conn.executemany(
                    """
                    INSERT OR IGNORE INTO numeric_pinyin_inventory (
                        pinyin_tone, initial, final, tone_number,
                        mapping_id, legacy_numeric_pinyin_id, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    missing_numeric_rows,
                )
            conn.executemany(
                """
                INSERT INTO phrase_inventory (
                    id, phrase, yime_code, phrase_frequency, phrase_length,
                    is_common_phrase, legacy_phrase_id, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                phrase_inventory_rows,
            )
            conn.executemany(
                """
                INSERT INTO phrase_readings (
                    id, source_name, phrase, marked_pinyin, numeric_pinyin,
                    reading_rank, comment, raw_line
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                source_reading_rows,
            )
            conn.executemany(
                """
                INSERT INTO phrase_pinyin_map (
                    phrase_id, pinyin_tone, reading_rank, source_file, source_note
                ) VALUES (?, ?, ?, ?, ?)
                """,
                phrase_map_rows,
            )
            phrase_count += len(phrase_inventory_rows)
            phrase_map_count += len(phrase_map_rows)
            conn.commit()

    return phrase_count, phrase_map_count, missing_numeric_count


def write_import_metadata(conn: sqlite3.Connection, phrase_count: int, phrase_map_count: int) -> None:
    rows = [
        (
            "phrase_source_strategy",
            "clone_unified_lexicon_primary_phrase_readings",
            "Derive the phrase inventory only from source_lexicon.sqlite3.",
        ),
        ("prototype_duozi_import_source", str(SOURCE_DB_PATH), "词语拼音来源数据库（phrase_readings）"),
        ("prototype_duozi_phrase_rows", str(phrase_count), "本次导入覆盖的词语读音行数"),
        ("prototype_duozi_phrase_map_rows", str(phrase_map_count), "本次导入的 phrase_pinyin_map 行数"),
        ("prototype_duozi_yime_source", "pinyin_yime_code", "词语导入时使用 canonical 拼音映射面拼装 yime_code，不再依赖 mapping_id"),
        ("prototype_duozi_phrase_preference_strategy", "explicit_phrase_reading_preference", "歧义词按显式默认读音表决定 runtime 默认读音"),
    ]
    conn.executemany(
        '''
        INSERT OR REPLACE INTO prototype_metadata (key, value, note, updated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ''',
        rows,
    )


def main() -> None:
    with sqlite3.connect(SOURCE_DB_PATH) as source_connection:
        is_bundle_source = uses_lexicon_bundle_schema(source_connection)
    if not is_bundle_source:
        raise RuntimeError(
            "production import requires unified source_lexicon.sqlite3; "
            "legacy source_pinyin.db schemas are not accepted"
        )
    source_files: list[tuple[str, str, str]] = []
    source_rows: list[tuple[int, str, str, str, str, int, str | None, str]] = []
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute('PRAGMA foreign_keys = ON')
        conn.execute('DROP TABLE IF EXISTS phrase_pinyin_map')
        conn.execute('DROP TABLE IF EXISTS phrase_inventory')
        conn.execute('DROP TABLE IF EXISTS yinjie_slot_decomposition')
        conn.execute('DROP TABLE IF EXISTS pinyin_yime_code')
        conn.execute('DROP TABLE IF EXISTS mapping_yime_code')
        apply_schema(conn)
        if is_bundle_source:
            phrase_count, phrase_map_count, _ = import_bundle_phrases_and_mappings(
                conn,
                SOURCE_DB_PATH,
            )
            copied_rows = phrase_count
        else:
            copied_rows = sync_source_phrase_table(conn, source_files, source_rows)
            phrase_count, phrase_map_count = import_phrases_and_mappings(conn, source_rows)
        write_import_metadata(conn, phrase_count, phrase_map_count)
        conn.commit()
    finally:
        conn.close()

    print(f"copied phrase_readings rows: {copied_rows}")
    print(f"imported phrases: {phrase_count}")
    print(f"phrase pinyin mappings: {phrase_map_count}")


if __name__ == "__main__":
    main()
