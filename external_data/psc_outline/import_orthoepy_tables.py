#!/usr/bin/env python3
"""Import the 1985 official orthoepy list and the 2016 draft comparison.

The official PDF is kept as the authority and visual verification source.  The
left column of the 2016 Word comparison supplies a machine-readable
transcription of the 1985 list; the right column is stored only as a draft
proposal.  This importer never rewrites the PSC observations or prototype
pronunciation databases.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import subprocess
import tempfile
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence


DATASET_KEY = "putonghua-orthoepy-1985-with-2016-draft"
EXTRACTION_VERSION = 1
SECTION_RE = re.compile(r"^[A-Z]$")
CJK_RE = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")
LATIN_TOKEN_RE = re.compile(
    r"[A-Za-züÜêÊāáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜńňǹḿ]+"
)
PINYIN_VOWELS = frozenset("aeiouüêāáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ")


@dataclass(frozen=True)
class SourceSnapshot:
    path: Path
    size: int
    sha256: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot(path: Path) -> SourceSnapshot:
    resolved = path.resolve(strict=True)
    return SourceSnapshot(resolved, resolved.stat().st_size, sha256_file(resolved))


def assert_unchanged(before: SourceSnapshot) -> None:
    after = snapshot(before.path)
    if (after.size, after.sha256) != (before.size, before.sha256):
        raise RuntimeError(f"source changed during import: {before.path}")


def normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFC", str(value or ""))
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    lines = [re.sub(r"[ \t\u3000]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def classify_row(source_row: int, old_text: str, proposed_text: str) -> str:
    if source_row == 1 and "原审音表" in old_text and "新审订" in proposed_text:
        return "header"
    visible = old_text or proposed_text
    if SECTION_RE.fullmatch(visible):
        return "section"
    if not old_text and not proposed_text:
        return "empty"
    if not old_text:
        return "addition"
    if proposed_text:
        return "revision"
    return "unchanged"


def is_explicit_deletion(text: str) -> bool:
    marker = re.sub(r"[\s（）()]", "", normalize_text(text))
    return marker == "此条删除"


def extract_headword(text: str) -> str:
    match = CJK_RE.search(text)
    return match.group(0) if match else ""


def extract_pinyin_tokens(text: str) -> tuple[str, ...]:
    result: list[str] = []
    for match in LATIN_TOKEN_RE.finditer(unicodedata.normalize("NFC", text)):
        token = match.group(0).lower()
        if not any(character in PINYIN_VOWELS for character in token):
            continue
        if token not in result:
            result.append(token)
    return tuple(result)


def count_pdf_pages(path: Path) -> int:
    try:
        from pypdf import PdfReader
    except ImportError as error:  # pragma: no cover - environment guard
        raise RuntimeError("pypdf is required to inspect the official PDF") from error
    return len(PdfReader(str(path)).pages)


def run_word_extractor(source: Path, extractor: Path) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="psc-orthoepy-") as temp_directory:
        output = Path(temp_directory) / "orthoepy-word.json"
        command = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(extractor),
            "-SourcePath",
            str(source),
            "-OutputPath",
            str(output),
        ]
        completed = subprocess.run(command, check=False, text=True, capture_output=True)
        if completed.returncode != 0:
            raise RuntimeError(
                "Word extraction failed:\n"
                + (completed.stdout or "")
                + (completed.stderr or "")
            )
        return dict(json.loads(output.read_text(encoding="utf-8")))


def load_extraction(path: Path) -> dict[str, object]:
    return dict(json.loads(path.read_text(encoding="utf-8")))


def validate_extraction(extraction: dict[str, object]) -> list[dict[str, object]]:
    rows = [dict(row) for row in extraction.get("rows", [])]
    expected = int(extraction.get("table_row_count", 0))
    if int(extraction.get("table_count", 0)) != 1:
        raise ValueError("Word source must contain exactly one table")
    if int(extraction.get("table_column_count", 0)) != 2:
        raise ValueError("Word comparison table must have exactly two columns")
    if expected <= 0 or len(rows) != expected:
        raise ValueError(f"row count mismatch: metadata={expected}, rows={len(rows)}")
    numbers = [int(row.get("source_row", 0)) for row in rows]
    if numbers != list(range(1, expected + 1)):
        raise ValueError("source rows must be contiguous and one-based")
    return rows


def create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS orthoepy_datasets (
            id INTEGER PRIMARY KEY,
            dataset_key TEXT NOT NULL UNIQUE,
            official_pdf_document_id INTEGER NOT NULL UNIQUE
                REFERENCES documents(id) ON DELETE RESTRICT,
            revision_doc_document_id INTEGER NOT NULL UNIQUE
                REFERENCES documents(id) ON DELETE RESTRICT,
            title TEXT NOT NULL,
            official_version TEXT NOT NULL,
            proposal_version TEXT NOT NULL,
            official_authority_status TEXT NOT NULL,
            proposal_authority_status TEXT NOT NULL,
            instructions_text TEXT NOT NULL,
            source_row_count INTEGER NOT NULL,
            official_entry_count INTEGER NOT NULL,
            proposed_entry_count INTEGER NOT NULL,
            proposed_change_count INTEGER NOT NULL,
            extraction_method TEXT NOT NULL,
            extraction_version INTEGER NOT NULL,
            imported_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS orthoepy_source_rows (
            id INTEGER PRIMARY KEY,
            dataset_id INTEGER NOT NULL
                REFERENCES orthoepy_datasets(id) ON DELETE CASCADE,
            source_row INTEGER NOT NULL,
            word_page_number INTEGER NOT NULL,
            section_label TEXT NOT NULL,
            row_kind TEXT NOT NULL CHECK(row_kind IN (
                'header','section','empty','unchanged','addition','revision'
            )),
            old_text_raw TEXT NOT NULL,
            old_text_nfc TEXT NOT NULL,
            proposed_text_raw TEXT NOT NULL,
            proposed_text_nfc TEXT NOT NULL,
            effective_proposed_text_nfc TEXT NOT NULL,
            evidence_json TEXT NOT NULL,
            UNIQUE(dataset_id, source_row)
        );

        CREATE TABLE IF NOT EXISTS orthoepy_entries (
            id INTEGER PRIMARY KEY,
            dataset_id INTEGER NOT NULL,
            version_key TEXT NOT NULL CHECK(version_key IN (
                'official_1985','draft_2016'
            )),
            authority_status TEXT NOT NULL CHECK(authority_status IN (
                'official','consultation_draft'
            )),
            source_row INTEGER NOT NULL,
            word_page_number INTEGER NOT NULL,
            section_label TEXT NOT NULL,
            entry_text TEXT NOT NULL,
            headword TEXT NOT NULL,
            pinyin_tokens_json TEXT NOT NULL,
            uniform_reading INTEGER NOT NULL CHECK(uniform_reading IN (0,1)),
            inherited_from_1985 INTEGER NOT NULL CHECK(inherited_from_1985 IN (0,1)),
            parse_status TEXT NOT NULL CHECK(parse_status IN (
                'machine_parsed','needs_review'
            )),
            evidence_json TEXT NOT NULL,
            UNIQUE(dataset_id, version_key, source_row),
            FOREIGN KEY(dataset_id, source_row)
                REFERENCES orthoepy_source_rows(dataset_id, source_row)
                ON DELETE CASCADE
        );

        DROP VIEW IF EXISTS orthoepy_1985_entries;
        CREATE VIEW orthoepy_1985_entries AS
        SELECT e.source_row, e.word_page_number, e.section_label, e.headword,
               e.entry_text, e.pinyin_tokens_json, e.uniform_reading,
               e.parse_status
          FROM orthoepy_entries AS e
          JOIN orthoepy_datasets AS d ON d.id=e.dataset_id
         WHERE d.dataset_key='putonghua-orthoepy-1985-with-2016-draft'
           AND e.version_key='official_1985'
         ORDER BY e.source_row;

        DROP VIEW IF EXISTS orthoepy_2016_proposed_entries;
        CREATE VIEW orthoepy_2016_proposed_entries AS
        SELECT e.source_row, e.word_page_number, e.section_label, e.headword,
               e.entry_text, e.pinyin_tokens_json, e.uniform_reading,
               e.inherited_from_1985, e.parse_status
          FROM orthoepy_entries AS e
          JOIN orthoepy_datasets AS d ON d.id=e.dataset_id
         WHERE d.dataset_key='putonghua-orthoepy-1985-with-2016-draft'
           AND e.version_key='draft_2016'
         ORDER BY e.source_row;

        DROP VIEW IF EXISTS orthoepy_revision_diff;
        CREATE VIEW orthoepy_revision_diff AS
        SELECT r.source_row, r.word_page_number, r.section_label, r.row_kind,
               CASE
                 WHEN r.row_kind='addition' THEN 'addition'
                 WHEN r.proposed_text_nfc LIKE '%此条删除%' THEN 'deletion'
                 ELSE 'revision'
               END AS change_operation,
               r.old_text_nfc AS official_1985_text,
               r.proposed_text_nfc AS draft_2016_text,
               old_entry.headword AS official_headword,
               new_entry.headword AS proposed_headword
          FROM orthoepy_source_rows AS r
          JOIN orthoepy_datasets AS d ON d.id=r.dataset_id
          LEFT JOIN orthoepy_entries AS old_entry
            ON old_entry.dataset_id=r.dataset_id
           AND old_entry.source_row=r.source_row
           AND old_entry.version_key='official_1985'
          LEFT JOIN orthoepy_entries AS new_entry
            ON new_entry.dataset_id=r.dataset_id
           AND new_entry.source_row=r.source_row
           AND new_entry.version_key='draft_2016'
         WHERE d.dataset_key='putonghua-orthoepy-1985-with-2016-draft'
           AND r.row_kind IN ('addition','revision')
         ORDER BY r.source_row;

        DROP VIEW IF EXISTS orthoepy_review_queue;
        CREATE VIEW orthoepy_review_queue AS
        SELECT e.version_key, e.source_row, e.word_page_number,
               e.section_label, e.headword, e.entry_text,
               e.pinyin_tokens_json, e.parse_status
          FROM orthoepy_entries AS e
          JOIN orthoepy_datasets AS d ON d.id=e.dataset_id
         WHERE d.dataset_key='putonghua-orthoepy-1985-with-2016-draft'
           AND e.parse_status='needs_review'
         ORDER BY e.version_key, e.source_row;

        DROP VIEW IF EXISTS orthoepy_import_summary;
        CREATE VIEW orthoepy_import_summary AS
        SELECT d.dataset_key, d.source_row_count, d.official_entry_count,
               d.proposed_entry_count, d.proposed_change_count,
               SUM(CASE WHEN e.version_key='official_1985'
                         AND e.parse_status='needs_review' THEN 1 ELSE 0 END)
                   AS official_entries_needing_review,
               SUM(CASE WHEN e.version_key='draft_2016'
                         AND e.parse_status='needs_review' THEN 1 ELSE 0 END)
                   AS proposed_entries_needing_review
          FROM orthoepy_datasets AS d
          LEFT JOIN orthoepy_entries AS e ON e.dataset_id=d.id
         WHERE d.dataset_key='putonghua-orthoepy-1985-with-2016-draft'
         GROUP BY d.id;
        """
    )


def ensure_document(
    connection: sqlite3.Connection,
    source: SourceSnapshot,
    page_count: int,
    now: str,
    extraction_label: str,
) -> int:
    row = connection.execute(
        "SELECT id FROM documents WHERE source_sha256=?", (source.sha256,)
    ).fetchone()
    if row is not None:
        return int(row[0])
    cursor = connection.execute(
        """
        INSERT INTO documents(
            source_path, source_filename, source_sha256, source_size,
            page_count, created_utc, updated_utc, ocr_engine, ocr_version,
            detection_model, recognition_model, language
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'not-applicable',
                  'not-applicable', 'zh-Hans')
        """,
        (
            str(source.path),
            source.path.name,
            source.sha256,
            source.size,
            page_count,
            now,
            now,
            extraction_label,
            str(EXTRACTION_VERSION),
        ),
    )
    return int(cursor.lastrowid)


def entry_payload(
    dataset_id: int,
    version_key: str,
    source_row: int,
    word_page_number: int,
    section_label: str,
    entry_text: str,
    inherited: bool,
    row_kind: str,
) -> tuple[object, ...]:
    headword = extract_headword(entry_text)
    tokens = extract_pinyin_tokens(entry_text)
    parse_status = "machine_parsed" if headword and tokens else "needs_review"
    authority = "official" if version_key == "official_1985" else "consultation_draft"
    evidence = {
        "source_row": source_row,
        "word_page_number": word_page_number,
        "row_kind": row_kind,
        "transcription_method": "2016_word_comparison_table",
        "official_pdf_verification": "not_yet_checked",
    }
    return (
        dataset_id,
        version_key,
        authority,
        source_row,
        word_page_number,
        section_label,
        entry_text,
        headword,
        json.dumps(tokens, ensure_ascii=False),
        int("统读" in entry_text),
        int(inherited),
        parse_status,
        json.dumps(evidence, ensure_ascii=False, sort_keys=True),
    )


def populate(
    connection: sqlite3.Connection,
    extraction: dict[str, object],
    official_pdf: SourceSnapshot,
    revision_doc: SourceSnapshot,
    official_pdf_pages: int,
) -> dict[str, int]:
    rows = validate_extraction(extraction)
    now = utc_now()
    create_schema(connection)
    connection.execute("DELETE FROM orthoepy_datasets WHERE dataset_key=?", (DATASET_KEY,))
    official_document_id = ensure_document(
        connection, official_pdf, official_pdf_pages, now, "visual-reference-only"
    )
    revision_document_id = ensure_document(
        connection,
        revision_doc,
        int(extraction.get("page_count", 0)),
        now,
        "word-com-read-only-table",
    )
    cursor = connection.execute(
        """
        INSERT INTO orthoepy_datasets(
            dataset_key, official_pdf_document_id, revision_doc_document_id,
            title, official_version, proposal_version,
            official_authority_status, proposal_authority_status,
            instructions_text, source_row_count, official_entry_count,
            proposed_entry_count, proposed_change_count, extraction_method,
            extraction_version, imported_utc
        ) VALUES (?, ?, ?, ?, '1985-12-27', '2016-05', 'official',
                  'consultation_draft', ?, ?, 0, 0, 0, ?, ?, ?)
        """,
        (
            DATASET_KEY,
            official_document_id,
            revision_document_id,
            "普通话异读词审音表",
            normalize_text(extraction.get("instructions_text", "")),
            len(rows),
            str(extraction.get("extraction_method", "word-com-read-only-table")),
            int(extraction.get("extraction_version", EXTRACTION_VERSION)),
            now,
        ),
    )
    dataset_id = int(cursor.lastrowid)
    section_label = ""
    official_entries = 0
    proposed_entries = 0
    changed_rows = 0
    for raw in rows:
        source_row = int(raw["source_row"])
        word_page = int(raw.get("word_page_number", 0))
        old_raw = str(raw.get("old_text", ""))
        proposed_raw = str(raw.get("proposed_text", ""))
        old = normalize_text(old_raw)
        proposed = normalize_text(proposed_raw)
        kind = classify_row(source_row, old, proposed)
        explicit_deletion = bool(old and proposed and is_explicit_deletion(proposed))
        if kind == "section":
            section_label = old or proposed
        effective = "" if explicit_deletion else (proposed if proposed else old)
        evidence = {
            "source_path": str(revision_doc.path),
            "source_sha256": revision_doc.sha256,
            "source_row": source_row,
            "word_page_number": word_page,
        }
        connection.execute(
            """
            INSERT INTO orthoepy_source_rows(
                dataset_id, source_row, word_page_number, section_label,
                row_kind, old_text_raw, old_text_nfc, proposed_text_raw,
                proposed_text_nfc, effective_proposed_text_nfc, evidence_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dataset_id,
                source_row,
                word_page,
                section_label,
                kind,
                old_raw,
                old,
                proposed_raw,
                proposed,
                effective,
                json.dumps(evidence, ensure_ascii=False, sort_keys=True),
            ),
        )
        if kind in {"addition", "revision"}:
            changed_rows += 1
        if kind in {"header", "section", "empty"}:
            continue
        if old:
            connection.execute(
                """
                INSERT INTO orthoepy_entries(
                    dataset_id, version_key, authority_status, source_row,
                    word_page_number, section_label, entry_text, headword,
                    pinyin_tokens_json, uniform_reading,
                    inherited_from_1985, parse_status, evidence_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                entry_payload(
                    dataset_id,
                    "official_1985",
                    source_row,
                    word_page,
                    section_label,
                    old,
                    False,
                    kind,
                ),
            )
            official_entries += 1
        if effective:
            connection.execute(
                """
                INSERT INTO orthoepy_entries(
                    dataset_id, version_key, authority_status, source_row,
                    word_page_number, section_label, entry_text, headword,
                    pinyin_tokens_json, uniform_reading,
                    inherited_from_1985, parse_status, evidence_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                entry_payload(
                    dataset_id,
                    "draft_2016",
                    source_row,
                    word_page,
                    section_label,
                    effective,
                    not bool(proposed),
                    kind,
                ),
            )
            proposed_entries += 1
    connection.execute(
        """
        UPDATE orthoepy_datasets
           SET official_entry_count=?, proposed_entry_count=?,
               proposed_change_count=?
         WHERE id=?
        """,
        (official_entries, proposed_entries, changed_rows, dataset_id),
    )
    review_count = int(
        connection.execute("SELECT COUNT(*) FROM orthoepy_review_queue").fetchone()[0]
    )
    return {
        "source_rows": len(rows),
        "official_entries": official_entries,
        "proposed_entries": proposed_entries,
        "proposed_changes": changed_rows,
        "entries_needing_review": review_count,
    }


def create_backup(database: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = database.with_name(
        f"{database.stem}.before_orthoepy_import.{timestamp}{database.suffix}"
    )
    source = sqlite3.connect(database)
    target = sqlite3.connect(backup)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    return backup


def database_has_dataset(connection: sqlite3.Connection) -> bool:
    table = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='orthoepy_datasets'"
    ).fetchone()
    if table is None:
        return False
    return connection.execute(
        "SELECT 1 FROM orthoepy_datasets WHERE dataset_key=?", (DATASET_KEY,)
    ).fetchone() is not None


def run_import(
    database: Path,
    official_pdf_path: Path,
    revision_doc_path: Path,
    extraction: dict[str, object],
    *,
    backup: bool = True,
) -> dict[str, object]:
    database = database.resolve()
    if not database.is_file():
        raise FileNotFoundError(database)
    official = snapshot(official_pdf_path)
    revision = snapshot(revision_doc_path)
    pdf_pages = count_pdf_pages(official.path)
    backup_path: Path | None = None
    probe = sqlite3.connect(database)
    try:
        already_imported = database_has_dataset(probe)
    finally:
        probe.close()
    if backup and not already_imported:
        backup_path = create_backup(database)
    connection = sqlite3.connect(database, timeout=30)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")
    try:
        with connection:
            counts = populate(connection, extraction, official, revision, pdf_pages)
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        if integrity != "ok":
            raise RuntimeError(f"SQLite integrity check failed: {integrity}")
    finally:
        connection.close()
    assert_unchanged(official)
    assert_unchanged(revision)
    return {
        "database": str(database),
        "backup": str(backup_path) if backup_path else None,
        "official_pdf": {
            "path": str(official.path),
            "sha256": official.sha256,
            "pages": pdf_pages,
        },
        "revision_doc": {
            "path": str(revision.path),
            "sha256": revision.sha256,
            "pages": int(extraction.get("page_count", 0)),
        },
        **counts,
        "integrity_check": "ok",
    }


def build_parser() -> argparse.ArgumentParser:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=root / "psc_outline_ocr.sqlite3")
    parser.add_argument(
        "--official-pdf", type=Path, default=root / "W020190416497956176438.pdf"
    )
    parser.add_argument(
        "--revision-doc", type=Path, default=root / "W020160606277722984732.doc"
    )
    parser.add_argument("--extracted-json", type=Path)
    parser.add_argument("--no-backup", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(__file__).resolve().parent
    extraction = (
        load_extraction(args.extracted_json)
        if args.extracted_json
        else run_word_extractor(args.revision_doc, root / "extract_orthoepy_word.ps1")
    )
    result = run_import(
        args.database,
        args.official_pdf,
        args.revision_doc,
        extraction,
        backup=not args.no_backup,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
