from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfWriter


MODULE_PATH = Path(__file__).with_name("import_orthoepy_tables.py")
SPEC = importlib.util.spec_from_file_location("import_orthoepy_tables", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def create_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        with connection:
            connection.executescript(
            """
            CREATE TABLE documents (
                id INTEGER PRIMARY KEY,
                source_path TEXT NOT NULL,
                source_filename TEXT NOT NULL,
                source_sha256 TEXT NOT NULL UNIQUE,
                source_size INTEGER NOT NULL,
                page_count INTEGER NOT NULL,
                created_utc TEXT NOT NULL,
                updated_utc TEXT NOT NULL,
                ocr_engine TEXT NOT NULL,
                ocr_version TEXT NOT NULL,
                detection_model TEXT NOT NULL,
                recognition_model TEXT NOT NULL,
                language TEXT NOT NULL
            );
            """
            )
    finally:
        connection.close()


def fixture_extraction() -> dict[str, object]:
    rows = [
        {"source_row": 1, "word_page_number": 1, "old_text": "原审音表", "proposed_text": "新审订"},
        {"source_row": 2, "word_page_number": 2, "old_text": "A", "proposed_text": ""},
        {"source_row": 3, "word_page_number": 3, "old_text": "癌ái（统读）", "proposed_text": ""},
        {"source_row": 4, "word_page_number": 3, "old_text": "薄（一）báo\n（二）bó", "proposed_text": "薄bó（统读）"},
        {"source_row": 5, "word_page_number": 4, "old_text": "", "proposed_text": "拜bái（统读）"},
        {"source_row": 6, "word_page_number": 4, "old_text": "旧jiù", "proposed_text": "（此条删除）"},
        {"source_row": 7, "word_page_number": 4, "old_text": "", "proposed_text": ""},
    ]
    return {
        "extraction_method": "fixture",
        "extraction_version": 1,
        "page_count": 4,
        "table_count": 1,
        "table_row_count": len(rows),
        "table_column_count": 2,
        "instructions_text": "右栏空白表示不作更改。",
        "rows": rows,
    }


class OrthoepyImportTests(unittest.TestCase):
    def test_classification_and_normalization(self) -> None:
        self.assertEqual(MODULE.classify_row(1, "原审音表", "新审订"), "header")
        self.assertEqual(MODULE.classify_row(2, "A", ""), "section")
        self.assertEqual(MODULE.classify_row(3, "癌ái（统读）", ""), "unchanged")
        self.assertEqual(MODULE.classify_row(4, "薄báo", "薄bó"), "revision")
        self.assertEqual(MODULE.classify_row(5, "", "拜bái"), "addition")
        self.assertTrue(MODULE.is_explicit_deletion("（此条删除）"))
        self.assertEqual(MODULE.extract_headword("薄（一）báo"), "薄")
        self.assertEqual(MODULE.extract_pinyin_tokens("薄（一）báo（二）bó"), ("báo", "bó"))

    def test_import_materializes_two_versions_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "psc.sqlite3"
            pdf = root / "official.pdf"
            doc = root / "revision.doc"
            create_database(database)
            writer = PdfWriter()
            writer.add_blank_page(width=612, height=792)
            with pdf.open("wb") as stream:
                writer.write(stream)
            doc.write_bytes(b"fixture word source")

            first = MODULE.run_import(
                database, pdf, doc, fixture_extraction(), backup=False
            )
            second = MODULE.run_import(
                database, pdf, doc, fixture_extraction(), backup=False
            )
            self.assertEqual(first["official_entries"], 3)
            self.assertEqual(first["proposed_entries"], 3)
            self.assertEqual(first["proposed_changes"], 3)
            self.assertEqual(second["official_entries"], 3)

            connection = sqlite3.connect(database)
            try:
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM orthoepy_datasets").fetchone()[0],
                    1,
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM orthoepy_source_rows").fetchone()[0],
                    7,
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM orthoepy_revision_diff").fetchone()[0],
                    3,
                )
                deletion = connection.execute(
                    """
                    SELECT change_operation, proposed_headword
                      FROM orthoepy_revision_diff WHERE source_row=6
                    """
                ).fetchone()
                self.assertEqual(deletion, ("deletion", None))
                inherited = connection.execute(
                    """
                    SELECT inherited_from_1985 FROM orthoepy_2016_proposed_entries
                     WHERE source_row=3
                    """
                ).fetchone()[0]
                self.assertEqual(inherited, 1)
                self.assertEqual(
                    connection.execute("PRAGMA integrity_check").fetchone()[0], "ok"
                )
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
