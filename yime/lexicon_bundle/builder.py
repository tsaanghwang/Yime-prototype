"""SQLite-backed builder for the unified, gated Yime source lexicon bundle."""

from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

from .gate import ReadingGate, is_han_text
from .parsers import (
    FrequencyRecord,
    ReadingRecord,
    iter_bcc_frequencies,
    iter_pypinyin_phrase_readings,
    iter_unihan_readings,
    iter_wanxiang_readings,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WANXIANG_FILES = (
    "zi.dict.yaml",
    "jichu.dict.yaml",
    "lianxiang.dict.yaml",
    "duoyin.dict.yaml",
    "diming.dict.yaml",
    "fangyan.dict.yaml",
    "huaxue.dict.yaml",
    "mingren.dict.yaml",
    "renming.dict.yaml",
    "shici.dict.yaml",
    "taifeng.dict.yaml",
    "wuzhong.dict.yaml",
    "yaopin.dict.yaml",
    "yiren.dict.yaml",
    "yixue.dict.yaml",
)


@dataclass(frozen=True)
class BundleInputs:
    unihan: Path
    pypinyin_phrases: Path
    bcc_words: Path
    bcc_chars: Path
    wanxiang_files: tuple[Path, ...]
    decoder_inventory: Path


@dataclass(frozen=True)
class BundleResult:
    output_dir: Path
    database: Path
    entries: Path
    rejections: Path
    unresolved_bcc: Path
    conflicts: Path
    manifest: Path
    accepted_readings: int
    output_entries: int
    unresolved_bcc_count: int


def default_inputs(wanxiang_root: Path | None = None) -> BundleInputs:
    root = wanxiang_root or REPO_ROOT.parent / "RIME-LMDG"
    return BundleInputs(
        unihan=REPO_ROOT / "internal_data" / "hanzi_pinyin" / "pinyin.txt",
        pypinyin_phrases=REPO_ROOT / "internal_data" / "phrase_pinyin" / "phrase_pinyin.txt",
        bcc_words=REPO_ROOT / "external_data" / "word_freq" / "merged_word_freq.txt",
        bcc_chars=REPO_ROOT / "external_data" / "char_freq" / "merged_char_freq.txt",
        wanxiang_files=tuple(root / "dicts" / name for name in DEFAULT_WANXIANG_FILES),
        decoder_inventory=REPO_ROOT / "yime" / "pinyin_normalized.json",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA journal_mode = WAL;
        PRAGMA synchronous = NORMAL;
        CREATE TABLE accepted_readings (
            text TEXT NOT NULL,
            marked TEXT NOT NULL,
            numeric TEXT NOT NULL,
            source TEXT NOT NULL,
            source_file TEXT NOT NULL,
            source_rank INTEGER NOT NULL,
            source_weight INTEGER,
            source_primary INTEGER NOT NULL,
            rule_ids TEXT NOT NULL,
            PRIMARY KEY (text, marked, source, source_file)
        ) WITHOUT ROWID;
        CREATE INDEX accepted_text_idx ON accepted_readings(text);
        CREATE TABLE bcc_frequency (
            text TEXT PRIMARY KEY,
            frequency INTEGER NOT NULL,
            source_file TEXT NOT NULL
        ) WITHOUT ROWID;
        CREATE TABLE rejections (
            source TEXT NOT NULL,
            source_file TEXT NOT NULL,
            line_number INTEGER NOT NULL,
            text TEXT NOT NULL,
            reading TEXT NOT NULL,
            rule_ids TEXT NOT NULL,
            reason TEXT NOT NULL
        );
        """
    )


def _import_readings(
    conn: sqlite3.Connection,
    gate: ReadingGate,
    records: Iterable[ReadingRecord],
) -> tuple[int, int]:
    accepted = rejected = 0
    for record in records:
        result = gate.admit(
            record.text,
            record.reading,
            codepoint_context=record.codepoint_context,
        )
        if not result.accepted:
            conn.execute(
                "INSERT INTO rejections VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    record.source,
                    record.source_file,
                    record.line_number,
                    record.text,
                    record.reading,
                    ",".join(result.rule_ids),
                    result.reason,
                ),
            )
            rejected += 1
            continue
        conn.execute(
            """
            INSERT INTO accepted_readings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(text, marked, source, source_file) DO UPDATE SET
                source_rank = MIN(source_rank, excluded.source_rank),
                source_weight = CASE
                    WHEN source_weight IS NULL THEN excluded.source_weight
                    WHEN excluded.source_weight IS NULL THEN source_weight
                    ELSE MAX(source_weight, excluded.source_weight)
                END,
                source_primary = MAX(source_primary, excluded.source_primary)
            """,
            (
                record.text,
                result.marked,
                result.numeric,
                record.source,
                record.source_file,
                record.source_rank,
                record.source_weight,
                int(record.source_primary),
                ",".join(result.rule_ids),
            ),
        )
        accepted += 1
    conn.commit()
    return accepted, rejected


def _import_frequencies(conn: sqlite3.Connection, records: Iterable[FrequencyRecord]) -> int:
    count = 0
    for record in records:
        if not is_han_text(record.text):
            continue
        conn.execute(
            """
            INSERT INTO bcc_frequency VALUES (?, ?, ?)
            ON CONFLICT(text) DO UPDATE SET
                frequency = MAX(frequency, excluded.frequency),
                source_file = CASE
                    WHEN excluded.frequency > frequency THEN excluded.source_file
                    ELSE source_file
                END
            """,
            (record.text, record.frequency, record.source_file),
        )
        count += 1
    conn.commit()
    return count


def _reading_groups(conn: sqlite3.Connection) -> Iterator[tuple[str, list[sqlite3.Row]]]:
    cursor = conn.execute(
        """
        SELECT a.*, COALESCE(f.frequency, 0) AS bcc_frequency
        FROM accepted_readings AS a
        LEFT JOIN bcc_frequency AS f USING (text)
        ORDER BY a.text, a.marked, a.source_rank, a.source
        """
    )
    current = ""
    rows: list[sqlite3.Row] = []
    for row in cursor:
        text = str(row["text"])
        if rows and text != current:
            yield current, rows
            rows = []
        current = text
        rows.append(row)
    if rows:
        yield current, rows


def _export_entries(conn: sqlite3.Connection, output_dir: Path) -> tuple[int, int]:
    entries_path = output_dir / "entries.tsv"
    conflicts_path = output_dir / "reading_conflicts.tsv"
    fields = [
        "text", "text_length", "pinyin_marked", "pinyin_numeric", "reading_rank",
        "is_primary", "bcc_frequency", "wanxiang_weight", "pinyin_sources", "rule_ids",
    ]
    output_count = conflict_count = 0
    with entries_path.open("w", encoding="utf-8", newline="") as entries_stream, conflicts_path.open(
        "w", encoding="utf-8", newline=""
    ) as conflicts_stream:
        writer = csv.DictWriter(entries_stream, fieldnames=fields, delimiter="\t")
        conflict_writer = csv.DictWriter(conflicts_stream, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        conflict_writer.writeheader()
        for text, source_rows in _reading_groups(conn):
            readings: dict[str, list[sqlite3.Row]] = defaultdict(list)
            for source_row in source_rows:
                readings[str(source_row["marked"])].append(source_row)
            ranked = sorted(
                readings.items(),
                key=lambda item: (
                    min(int(row["source_rank"]) for row in item[1]),
                    -max(int(row["source_primary"]) for row in item[1]),
                    -max(int(row["source_weight"] or 0) for row in item[1]),
                    item[0],
                ),
            )
            for rank, (marked, rows) in enumerate(ranked, start=1):
                sources = sorted({str(row["source"]) for row in rows})
                rules = sorted(
                    {rule for row in rows for rule in str(row["rule_ids"]).split(",") if rule}
                )
                wanxiang_weight = max(
                    (int(row["source_weight"] or 0) for row in rows if row["source"] == "wanxiang"),
                    default=0,
                )
                exported = {
                    "text": text,
                    "text_length": len(text),
                    "pinyin_marked": marked,
                    "pinyin_numeric": str(rows[0]["numeric"]),
                    "reading_rank": rank,
                    "is_primary": int(rank == 1),
                    "bcc_frequency": int(rows[0]["bcc_frequency"]),
                    "wanxiang_weight": wanxiang_weight,
                    "pinyin_sources": ",".join(sources),
                    "rule_ids": ",".join(rules),
                }
                writer.writerow(exported)
                if len(ranked) > 1:
                    conflict_writer.writerow(exported)
                    conflict_count += 1
                output_count += 1
    return output_count, conflict_count


def _export_rejections(conn: sqlite3.Connection, output_dir: Path) -> int:
    path = output_dir / "rejected_readings.tsv"
    fields = ["source", "source_file", "line_number", "text", "reading", "rule_ids", "reason"]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        writer.writerow(fields)
        count = 0
        for row in conn.execute(
            "SELECT source, source_file, line_number, text, reading, rule_ids, reason FROM rejections ORDER BY source, source_file, line_number"
        ):
            writer.writerow(tuple(row))
            count += 1
    return count


def _export_unresolved_bcc(conn: sqlite3.Connection, output_dir: Path) -> int:
    path = output_dir / "unresolved_bcc.tsv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        writer.writerow(("text", "text_length", "bcc_frequency", "reason"))
        count = 0
        for text, frequency in conn.execute(
            """
            SELECT f.text, f.frequency
            FROM bcc_frequency AS f
            WHERE NOT EXISTS (
                SELECT 1 FROM accepted_readings AS a WHERE a.text = f.text
            )
            ORDER BY f.frequency DESC, f.text
            """
        ):
            writer.writerow((text, len(str(text)), frequency, "no_gated_reading_source"))
            count += 1
    return count


def build_bundle(inputs: BundleInputs, output_dir: Path) -> BundleResult:
    source_paths = (
        inputs.unihan,
        inputs.pypinyin_phrases,
        inputs.bcc_words,
        inputs.bcc_chars,
        inputs.decoder_inventory,
        *inputs.wanxiang_files,
    )
    missing = [str(path) for path in source_paths if not path.is_file()]
    if missing:
        raise FileNotFoundError("missing lexicon bundle inputs: " + "; ".join(missing))

    output_dir.mkdir(parents=True, exist_ok=True)
    database = output_dir / "source_lexicon.sqlite3"
    if database.exists():
        database.unlink()
    conn = sqlite3.connect(database)
    conn.row_factory = sqlite3.Row
    _create_schema(conn)
    gate = ReadingGate(inputs.decoder_inventory)

    source_stats: dict[str, dict[str, int]] = {}
    accepted_total = 0
    for name, records in (
        ("unihan", iter_unihan_readings(inputs.unihan)),
        ("pypinyin", iter_pypinyin_phrase_readings(inputs.pypinyin_phrases)),
    ):
        accepted, rejected = _import_readings(conn, gate, records)
        source_stats[name] = {"accepted": accepted, "rejected": rejected}
        accepted_total += accepted

    wanxiang_accepted = wanxiang_rejected = 0
    for path in inputs.wanxiang_files:
        accepted, rejected = _import_readings(conn, gate, iter_wanxiang_readings(path))
        wanxiang_accepted += accepted
        wanxiang_rejected += rejected
    source_stats["wanxiang"] = {
        "accepted": wanxiang_accepted,
        "rejected": wanxiang_rejected,
    }
    accepted_total += wanxiang_accepted

    bcc_rows = _import_frequencies(conn, iter_bcc_frequencies(inputs.bcc_words))
    bcc_rows += _import_frequencies(conn, iter_bcc_frequencies(inputs.bcc_chars))

    output_entries, conflict_rows = _export_entries(conn, output_dir)
    rejected_rows = _export_rejections(conn, output_dir)
    unresolved_count = _export_unresolved_bcc(conn, output_dir)
    unique_bcc = int(conn.execute("SELECT COUNT(*) FROM bcc_frequency").fetchone()[0])
    unique_texts = int(conn.execute("SELECT COUNT(DISTINCT text) FROM accepted_readings").fetchone()[0])
    conn.close()

    manifest_path = output_dir / "manifest.json"
    manifest = {
        "schema_version": "yime-gated-source-lexicon-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "policy": {
            "frequency": "BCC integer counts are preserved; absent BCC evidence remains 0.",
            "wanxiang_weight": "Kept separately; never treated as a BCC count.",
            "reading": "Shared first-round source compliance plus current decoder inventory.",
            "unresolved": "No per-character pronunciation guessing for unmatched BCC terms.",
            "excluded_wanxiang_files": ["cuoyin.dict.yaml", "mixed.dict.yaml"],
        },
        "counts": {
            "accepted_source_rows": accepted_total,
            "unique_accepted_texts": unique_texts,
            "output_text_readings": output_entries,
            "reading_conflict_rows": conflict_rows,
            "rejected_source_rows": rejected_rows,
            "bcc_input_rows": bcc_rows,
            "unique_bcc_texts": unique_bcc,
            "unresolved_bcc_texts": unresolved_count,
        },
        "sources": [
            {"path": str(path), "sha256": _sha256(path), "bytes": path.stat().st_size}
            for path in source_paths
        ],
        "source_gate_counts": source_stats,
        "outputs": {
            "entries": "entries.tsv",
            "rejected_readings": "rejected_readings.tsv",
            "unresolved_bcc": "unresolved_bcc.tsv",
            "reading_conflicts": "reading_conflicts.tsv",
            "database": "source_lexicon.sqlite3",
        },
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return BundleResult(
        output_dir=output_dir,
        database=database,
        entries=output_dir / "entries.tsv",
        rejections=output_dir / "rejected_readings.tsv",
        unresolved_bcc=output_dir / "unresolved_bcc.tsv",
        conflicts=output_dir / "reading_conflicts.tsv",
        manifest=manifest_path,
        accepted_readings=accepted_total,
        output_entries=output_entries,
        unresolved_bcc_count=unresolved_count,
    )
