import sqlite3
import tempfile
import unittest
from pathlib import Path

from psc_outline_review_tool import ReviewStore


CORE_SCHEMA = """
CREATE TABLE documents (id INTEGER PRIMARY KEY);
CREATE TABLE pages (
    document_id INTEGER NOT NULL,
    page_number INTEGER NOT NULL,
    table_number INTEGER,
    image_path TEXT,
    image_width INTEGER,
    image_height INTEGER,
    PRIMARY KEY(document_id, page_number)
);
CREATE TABLE entries (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL,
    table_number INTEGER,
    source_index INTEGER NOT NULL,
    page_number INTEGER NOT NULL,
    column_number INTEGER NOT NULL,
    row_order INTEGER NOT NULL,
    index_origin TEXT NOT NULL,
    hanzi TEXT,
    pinyin_raw TEXT,
    pinyin_nfc TEXT,
    raw_text TEXT NOT NULL,
    minimum_confidence REAL,
    mean_confidence REAL,
    status TEXT NOT NULL,
    evidence_span_ids_json TEXT NOT NULL
);
CREATE TABLE issues (
    id INTEGER PRIMARY KEY,
    document_id INTEGER,
    page_number INTEGER,
    table_number INTEGER,
    source_index INTEGER,
    code TEXT,
    message TEXT
);
CREATE TABLE ocr_spans (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL,
    page_number INTEGER NOT NULL,
    column_number INTEGER NOT NULL,
    span_order INTEGER NOT NULL,
    text TEXT NOT NULL,
    confidence REAL NOT NULL,
    x1 REAL NOT NULL,
    y1 REAL NOT NULL,
    x2 REAL NOT NULL,
    y2 REAL NOT NULL
);
"""


class PinyinBatchAssistTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Path(self.temp_dir.name) / "review.sqlite3"
        connection = sqlite3.connect(self.database)
        connection.executescript(CORE_SCHEMA)
        connection.executemany(
            "INSERT INTO pages VALUES(?,?,?,?,?,?)",
            [
                (1, 1, 2, "", 900, 1265),
                (1, 2, 2, "", 900, 1265),
            ],
        )
        # An accepted single-character headword is the local authoritative
        # signal that 行 is polyphonic.
        connection.execute(
            """
            INSERT INTO entries VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                1,
                1,
                1,
                100,
                1,
                1,
                1,
                "ocr",
                "行",
                "xíng/háng",
                "xíng/háng",
                "行 xíng/háng",
                0.999,
                0.999,
                "accepted",
                "[10]",
            ),
        )
        # The target Hanzi ends column 3. Its pinyin is the first unassigned
        # OCR span in column 1 of the next page.
        connection.execute(
            "INSERT INTO entries VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                2,
                1,
                2,
                440,
                1,
                3,
                2,
                "ocr",
                "行路",
                "",
                "",
                "行路",
                0.998,
                0.999,
                "needs_review",
                "[20]",
            ),
        )
        connection.executemany(
            "INSERT INTO ocr_spans VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            [
                (10, 1, 1, 1, 1, "行 xíng/háng", 0.999, 70, 100, 200, 130),
                (20, 1, 1, 3, 2, "行路", 0.998, 660, 1225, 760, 1256),
                (21, 1, 2, 1, 3, "xínglù", 0.997, 80, 12, 170, 40),
                # This belongs to the first normal row and must not be joined.
                (22, 1, 2, 1, 4, "xià", 0.999, 145, 45, 200, 72),
            ],
        )
        connection.commit()
        connection.close()
        self.store = ReviewStore(self.database)

    def tearDown(self) -> None:
        self.store.close()
        self.temp_dir.cleanup()

    def test_stages_cross_page_proposal_and_flags_polyphonic_hanzi(self) -> None:
        summary = self.store.prepare_pinyin_proposals()

        self.assertEqual(summary["proposals"], 1)
        self.assertEqual(summary["by_source"], {"ocr_next_page": 1})
        self.assertEqual(summary["manual_review"], 1)
        item = next(item for item in self.store.load_items() if item.entry_id == 2)
        self.assertIsNotNone(item.proposal)
        assert item.proposal is not None
        self.assertEqual(item.proposal.text, "xínglù")
        self.assertEqual(item.proposal.span_ids, [21])
        self.assertEqual(item.proposal.review_class, "manual_review")
        self.assertTrue(any(flag.startswith("多音字 行") for flag in item.proposal.flags))
        self.assertEqual(
            self.store.conn.execute(
                "SELECT COUNT(*) FROM manual_corrections"
            ).fetchone()[0],
            0,
        )

    def test_accept_and_revert_use_existing_manual_audit_tables(self) -> None:
        self.store.prepare_pinyin_proposals()
        item = next(item for item in self.store.load_items() if item.entry_id == 2)
        assert item.proposal is not None
        original_entry = tuple(
            self.store.conn.execute(
                "SELECT hanzi, pinyin_raw, status FROM entries WHERE id=2"
            ).fetchone()
        )

        self.store.save(
            item,
            "corrected",
            item.hanzi,
            item.proposal.text,
            "accepted staged proposal",
            action="accept_pinyin_proposal",
        )
        saved = self.store.conn.execute(
            "SELECT * FROM manual_corrections WHERE entry_id_at_review=2"
        ).fetchone()
        self.assertEqual(saved["corrected_pinyin"], "xínglù")
        self.assertEqual(
            self.store.conn.execute(
                "SELECT action FROM manual_review_history ORDER BY id DESC LIMIT 1"
            ).fetchone()[0],
            "accept_pinyin_proposal",
        )
        self.assertEqual(
            tuple(
                self.store.conn.execute(
                    "SELECT hanzi, pinyin_raw, status FROM entries WHERE id=2"
                ).fetchone()
            ),
            original_entry,
        )

        reviewed_item = next(
            item for item in self.store.load_items() if item.entry_id == 2
        )
        self.store.clear(reviewed_item)
        self.assertEqual(
            self.store.conn.execute(
                "SELECT COUNT(*) FROM manual_corrections WHERE entry_id_at_review=2"
            ).fetchone()[0],
            0,
        )
        self.assertEqual(
            self.store.conn.execute(
                "SELECT action FROM manual_review_history ORDER BY id DESC LIMIT 1"
            ).fetchone()[0],
            "clear",
        )
        # Revert removes only the accepted manual decision; the staged proposal
        # remains available to inspect or accept again.
        proposal = self.store.conn.execute(
            "SELECT proposed_pinyin FROM pinyin_proposals WHERE entry_id_at_proposal=2"
        ).fetchone()
        self.assertEqual(proposal[0], "xínglù")

    def test_regeneration_is_idempotent(self) -> None:
        first = self.store.prepare_pinyin_proposals()
        second = self.store.prepare_pinyin_proposals()

        self.assertEqual(first["changes"]["created"], 1)
        self.assertEqual(second["changes"]["unchanged"], 1)
        self.assertEqual(
            self.store.conn.execute(
                "SELECT COUNT(*) FROM pinyin_proposal_history"
            ).fetchone()[0],
            1,
        )

    def test_read_only_report_flags_reparsed_id_and_original_text(self) -> None:
        item = next(item for item in self.store.load_items() if item.entry_id == 2)
        self.store.save(item, "corrected", "行路", "xínglù", "reviewed")
        # Simulate the latest reparse replacing the entry at the same stable
        # document/table/source-index key.
        self.store.conn.execute(
            """
            UPDATE entries
               SET id=202, hanzi='行旅', pinyin_raw='xínglǚ', status='accepted'
             WHERE id=2
            """
        )
        self.store.conn.commit()
        self.store.close()
        self.store = ReviewStore(self.database, read_only=True)
        before_entries = [tuple(row) for row in self.store.conn.execute("SELECT * FROM entries")]
        before_spans = [tuple(row) for row in self.store.conn.execute("SELECT * FROM ocr_spans")]

        report = self.store.manual_correction_validation_report()

        self.assertEqual(report["status"], "stale")
        self.assertEqual(report["checked_corrections"], 1)
        self.assertEqual(report["stale_corrections"], 1)
        mismatch = report["mismatches"][0]
        self.assertEqual(
            mismatch["mismatched_fields"],
            ["entry_id_at_review", "original_hanzi", "original_pinyin"],
        )
        self.assertEqual(mismatch["stored"]["entry_id"], 2)
        self.assertEqual(mismatch["current"]["entry_id"], 202)
        self.assertEqual(mismatch["stored"]["original_hanzi"], "行路")
        self.assertEqual(mismatch["current"]["hanzi"], "行旅")
        self.assertEqual(
            [tuple(row) for row in self.store.conn.execute("SELECT * FROM entries")],
            before_entries,
        )
        self.assertEqual(
            [tuple(row) for row in self.store.conn.execute("SELECT * FROM ocr_spans")],
            before_spans,
        )

        # The GUI queue includes stale corrections even if the current parser
        # no longer marks that entry as needing review.
        stale_item = next(item for item in self.store.load_items() if item.entry_id == 202)
        self.assertTrue(stale_item.has_stale_correction)
        self.assertEqual(stale_item.stale_correction_fields, mismatch["mismatched_fields"])

    def test_validation_report_keeps_matching_correction_valid(self) -> None:
        item = next(item for item in self.store.load_items() if item.entry_id == 2)
        self.store.save(item, "confirmed", item.hanzi, item.pinyin, "checked")

        report = self.store.manual_correction_validation_report()

        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["checked_corrections"], 1)
        self.assertEqual(report["valid_corrections"], 1)
        self.assertEqual(report["stale_corrections"], 0)
        self.assertEqual(report["mismatches"], [])

    def test_validation_report_flags_correction_whose_entry_disappeared(self) -> None:
        item = next(item for item in self.store.load_items() if item.entry_id == 2)
        self.store.save(item, "unresolved", item.hanzi, item.pinyin, "missing later")
        self.store.conn.execute("DELETE FROM entries WHERE id=2")
        self.store.conn.commit()

        report = self.store.manual_correction_validation_report()

        self.assertEqual(report["stale_corrections"], 1)
        self.assertEqual(report["missing_entries"], 1)
        self.assertEqual(report["mismatch_counts"]["missing_entry"], 1)
        self.assertEqual(report["mismatches"][0]["mismatched_fields"], ["missing_entry"])
        self.assertIsNone(report["mismatches"][0]["current"])


if __name__ == "__main__":
    unittest.main()
