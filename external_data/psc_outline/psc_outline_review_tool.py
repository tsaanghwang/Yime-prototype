#!/usr/bin/env python3
"""Small GUI for reviewing OCR exceptions in a PSC outline SQLite database.

The tool never rewrites ``entries``, ``ocr_spans`` or the stored OCR JSON.
Manual decisions are stored separately in ``manual_corrections`` and every
change is appended to ``manual_review_history``.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


DECISION_LABELS = {
    "pending": "待处理",
    "corrected": "已修改",
    "confirmed": "确认无误",
    "unresolved": "暂无法判断",
}

PROPOSAL_LABELS = {
    "ready": "建议可复核",
    "manual_review": "建议需重点复核",
}

PROPOSAL_SOURCE_LABELS = {
    "ocr_same_column": "同栏换行 OCR",
    "ocr_next_column": "跨栏换行 OCR",
    "ocr_next_page": "跨页换行 OCR",
}

STALE_CORRECTION_FIELD_LABELS = {
    "missing_entry": "当前条目不存在",
    "entry_id_at_review": "条目 ID 已变化",
    "original_hanzi": "原汉字已变化",
    "original_pinyin": "原拼音已变化",
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


@dataclass
class PinyinProposal:
    text: str
    minimum_confidence: float
    span_ids: list[int]
    source: str
    review_class: str
    flags: list[str]
    batch_id: str


@dataclass
class ReviewItem:
    document_id: int
    entry_id: int
    table_number: int
    source_index: int
    page_number: int
    column_number: int
    hanzi: str
    pinyin: str
    raw_text: str
    index_origin: str
    minimum_confidence: float | None
    evidence_span_ids: list[int]
    issue_summary: str
    image_path: str
    decision: str
    corrected_hanzi: str
    corrected_pinyin: str
    review_note: str
    proposal: PinyinProposal | None
    stale_correction_fields: list[str]
    correction_entry_id_at_review: int | None
    correction_original_hanzi: str | None
    correction_original_pinyin: str | None

    @property
    def key(self) -> tuple[int, int, int]:
        return self.document_id, self.table_number, self.source_index

    @property
    def has_stale_correction(self) -> bool:
        return bool(self.stale_correction_fields)


@dataclass
class ContinuationSuggestion:
    text: str
    minimum_confidence: float
    span_ids: list[int]
    boxes: list[sqlite3.Row]
    source: str = "ocr_same_column"
    page_number: int | None = None
    column_number: int | None = None


class ReviewStore:
    def __init__(self, database: Path, *, read_only: bool = False) -> None:
        self.database = database.resolve()
        self.read_only = read_only
        if read_only:
            self.conn = sqlite3.connect(
                f"file:{self.database.as_posix()}?mode=ro", uri=True
            )
        else:
            self.conn = sqlite3.connect(self.database)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA busy_timeout=5000")
        if not read_only:
            self._ensure_schema()

    def close(self) -> None:
        self.conn.close()

    def _ensure_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS manual_corrections (
                document_id INTEGER NOT NULL,
                table_number INTEGER NOT NULL,
                source_index INTEGER NOT NULL,
                entry_id_at_review INTEGER NOT NULL,
                original_hanzi TEXT,
                original_pinyin TEXT,
                corrected_hanzi TEXT,
                corrected_pinyin TEXT,
                decision TEXT NOT NULL CHECK (
                    decision IN ('corrected', 'confirmed', 'unresolved')
                ),
                review_note TEXT,
                reviewer TEXT NOT NULL DEFAULT 'manual',
                reviewed_at_utc TEXT NOT NULL,
                PRIMARY KEY (document_id, table_number, source_index)
            );

            CREATE TABLE IF NOT EXISTS manual_review_history (
                id INTEGER PRIMARY KEY,
                document_id INTEGER NOT NULL,
                table_number INTEGER NOT NULL,
                source_index INTEGER NOT NULL,
                action TEXT NOT NULL,
                previous_json TEXT,
                current_json TEXT,
                occurred_at_utc TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_manual_review_history_entry
                ON manual_review_history(
                    document_id, table_number, source_index, occurred_at_utc
                );

            CREATE TABLE IF NOT EXISTS pinyin_proposals (
                document_id INTEGER NOT NULL,
                table_number INTEGER NOT NULL,
                source_index INTEGER NOT NULL,
                entry_id_at_proposal INTEGER NOT NULL,
                original_hanzi TEXT NOT NULL,
                original_pinyin TEXT NOT NULL,
                proposed_pinyin TEXT NOT NULL,
                source TEXT NOT NULL,
                minimum_confidence REAL NOT NULL,
                evidence_span_ids_json TEXT NOT NULL,
                review_class TEXT NOT NULL CHECK (
                    review_class IN ('ready', 'manual_review')
                ),
                flags_json TEXT NOT NULL,
                batch_id TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                PRIMARY KEY (document_id, table_number, source_index)
            );

            CREATE TABLE IF NOT EXISTS pinyin_proposal_history (
                id INTEGER PRIMARY KEY,
                document_id INTEGER NOT NULL,
                table_number INTEGER NOT NULL,
                source_index INTEGER NOT NULL,
                action TEXT NOT NULL,
                previous_json TEXT,
                current_json TEXT,
                occurred_at_utc TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_pinyin_proposals_review_class
                ON pinyin_proposals(review_class, table_number, source_index);

            CREATE INDEX IF NOT EXISTS idx_pinyin_proposal_history_entry
                ON pinyin_proposal_history(
                    document_id, table_number, source_index, occurred_at_utc
                );

            CREATE VIEW IF NOT EXISTS manually_reviewed_entries AS
            SELECT
                e.document_id,
                e.table_number,
                e.source_index,
                e.page_number,
                e.column_number,
                e.hanzi AS ocr_hanzi,
                e.pinyin_raw AS ocr_pinyin,
                CASE
                    WHEN c.decision IN ('corrected', 'confirmed')
                    THEN c.corrected_hanzi
                    ELSE e.hanzi
                END AS reviewed_hanzi,
                CASE
                    WHEN c.decision IN ('corrected', 'confirmed')
                    THEN c.corrected_pinyin
                    ELSE e.pinyin_raw
                END AS reviewed_pinyin,
                COALESCE(c.decision, 'pending') AS review_decision,
                c.review_note,
                c.reviewed_at_utc
            FROM entries AS e
            LEFT JOIN manual_corrections AS c
              ON c.document_id = e.document_id
             AND c.table_number = e.table_number
             AND c.source_index = e.source_index;
            """
        )
        self.conn.commit()

    def _table_exists(self, name: str) -> bool:
        return (
            self.conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
            ).fetchone()
            is not None
        )

    def manual_correction_validation_report(self) -> dict[str, Any]:
        """Compare review-time snapshots with current entries without writing.

        A correction is stale when the entry at its stable document/table/index
        key disappeared, received a new row id, or its original Hanzi/Pinyin no
        longer exactly matches the values that were reviewed.
        """
        mismatch_counts = {
            "missing_entry": 0,
            "entry_id_at_review": 0,
            "original_hanzi": 0,
            "original_pinyin": 0,
        }
        if not self._table_exists("manual_corrections"):
            return {
                "database": str(self.database),
                "status": "ok",
                "checked_corrections": 0,
                "valid_corrections": 0,
                "stale_corrections": 0,
                "missing_entries": 0,
                "mismatch_counts": mismatch_counts,
                "mismatches": [],
            }

        rows = self.conn.execute(
            """
            SELECT
                c.document_id,
                c.table_number,
                c.source_index,
                c.entry_id_at_review,
                c.original_hanzi,
                c.original_pinyin,
                c.corrected_hanzi,
                c.corrected_pinyin,
                c.decision,
                c.reviewed_at_utc,
                e.id AS current_entry_id,
                e.hanzi AS current_hanzi,
                e.pinyin_raw AS current_pinyin
            FROM manual_corrections AS c
            LEFT JOIN entries AS e
              ON e.document_id = c.document_id
             AND e.table_number = c.table_number
             AND e.source_index = c.source_index
            ORDER BY c.document_id, c.table_number, c.source_index
            """
        ).fetchall()

        mismatches: list[dict[str, Any]] = []
        for row in rows:
            fields: list[str] = []
            current_entry_id = row["current_entry_id"]
            if current_entry_id is None:
                fields.append("missing_entry")
            else:
                if row["entry_id_at_review"] != current_entry_id:
                    fields.append("entry_id_at_review")
                if row["original_hanzi"] != row["current_hanzi"]:
                    fields.append("original_hanzi")
                if row["original_pinyin"] != row["current_pinyin"]:
                    fields.append("original_pinyin")
            if not fields:
                continue
            for field in fields:
                mismatch_counts[field] += 1
            mismatches.append(
                {
                    "document_id": int(row["document_id"]),
                    "table_number": int(row["table_number"]),
                    "source_index": int(row["source_index"]),
                    "decision": str(row["decision"]),
                    "reviewed_at_utc": str(row["reviewed_at_utc"]),
                    "mismatched_fields": fields,
                    "stored": {
                        "entry_id": int(row["entry_id_at_review"]),
                        "original_hanzi": row["original_hanzi"],
                        "original_pinyin": row["original_pinyin"],
                        "corrected_hanzi": row["corrected_hanzi"],
                        "corrected_pinyin": row["corrected_pinyin"],
                    },
                    "current": (
                        {
                            "entry_id": int(current_entry_id),
                            "hanzi": row["current_hanzi"],
                            "pinyin": row["current_pinyin"],
                        }
                        if current_entry_id is not None
                        else None
                    ),
                }
            )

        checked = len(rows)
        stale = len(mismatches)
        return {
            "database": str(self.database),
            "status": "stale" if stale else "ok",
            "checked_corrections": checked,
            "valid_corrections": checked - stale,
            "stale_corrections": stale,
            "missing_entries": mismatch_counts["missing_entry"],
            "mismatch_counts": mismatch_counts,
            "mismatches": mismatches,
        }

    def load_items(self) -> list[ReviewItem]:
        has_proposals = self._table_exists("pinyin_proposals")
        proposal_columns = (
            """
                pr.proposed_pinyin,
                pr.source AS proposal_source,
                pr.minimum_confidence AS proposal_confidence,
                pr.evidence_span_ids_json AS proposal_span_ids_json,
                pr.review_class AS proposal_review_class,
                pr.flags_json AS proposal_flags_json,
                pr.batch_id AS proposal_batch_id,
            """
            if has_proposals
            else """
                NULL AS proposed_pinyin,
                NULL AS proposal_source,
                NULL AS proposal_confidence,
                NULL AS proposal_span_ids_json,
                NULL AS proposal_review_class,
                NULL AS proposal_flags_json,
                NULL AS proposal_batch_id,
            """
        )
        proposal_join = (
            """
            LEFT JOIN pinyin_proposals AS pr
              ON pr.document_id = e.document_id
             AND pr.table_number = e.table_number
             AND pr.source_index = e.source_index
            """
            if has_proposals
            else ""
        )
        rows = self.conn.execute(
            f"""
            SELECT
                e.document_id,
                e.id AS entry_id,
                e.table_number,
                e.source_index,
                e.page_number,
                e.column_number,
                COALESCE(e.hanzi, '') AS hanzi,
                COALESCE(e.pinyin_raw, '') AS pinyin,
                e.raw_text,
                e.index_origin,
                e.minimum_confidence,
                e.evidence_span_ids_json,
                p.image_path,
                COALESCE(c.decision, 'pending') AS decision,
                COALESCE(c.corrected_hanzi, e.hanzi, '') AS corrected_hanzi,
                COALESCE(c.corrected_pinyin, e.pinyin_raw, '') AS corrected_pinyin,
                COALESCE(c.review_note, '') AS review_note,
                c.entry_id_at_review AS correction_entry_id_at_review,
                c.original_hanzi AS correction_original_hanzi,
                c.original_pinyin AS correction_original_pinyin,
                e.hanzi AS current_hanzi_raw,
                e.pinyin_raw AS current_pinyin_raw,
                {proposal_columns}
                COALESCE((
                    SELECT group_concat(i.code || '：' || i.message, char(10))
                      FROM issues AS i
                     WHERE i.document_id = e.document_id
                       AND i.page_number = e.page_number
                       AND i.table_number = e.table_number
                       AND i.source_index = e.source_index
                ), '') AS issue_summary
            FROM entries AS e
            JOIN pages AS p
              ON p.document_id = e.document_id
             AND p.page_number = e.page_number
            LEFT JOIN manual_corrections AS c
              ON c.document_id = e.document_id
             AND c.table_number = e.table_number
             AND c.source_index = e.source_index
            {proposal_join}
            WHERE e.status = 'needs_review'
               OR (
                    c.decision IS NOT NULL
                AND (
                       c.entry_id_at_review IS NOT e.id
                    OR c.original_hanzi IS NOT e.hanzi
                    OR c.original_pinyin IS NOT e.pinyin_raw
                )
               )
            ORDER BY e.document_id, e.table_number, e.source_index
            """
        ).fetchall()
        return [
            ReviewItem(
                document_id=int(row["document_id"]),
                entry_id=int(row["entry_id"]),
                table_number=int(row["table_number"]),
                source_index=int(row["source_index"]),
                page_number=int(row["page_number"]),
                column_number=int(row["column_number"]),
                hanzi=str(row["hanzi"]),
                pinyin=str(row["pinyin"]),
                raw_text=str(row["raw_text"]),
                index_origin=str(row["index_origin"]),
                minimum_confidence=(
                    float(row["minimum_confidence"])
                    if row["minimum_confidence"] is not None
                    else None
                ),
                evidence_span_ids=json.loads(row["evidence_span_ids_json"]),
                issue_summary=str(row["issue_summary"]),
                image_path=str(row["image_path"] or ""),
                decision=str(row["decision"]),
                corrected_hanzi=str(row["corrected_hanzi"]),
                corrected_pinyin=str(row["corrected_pinyin"]),
                review_note=str(row["review_note"]),
                proposal=(
                    PinyinProposal(
                        text=str(row["proposed_pinyin"]),
                        minimum_confidence=float(row["proposal_confidence"]),
                        span_ids=json.loads(row["proposal_span_ids_json"]),
                        source=str(row["proposal_source"]),
                        review_class=str(row["proposal_review_class"]),
                        flags=json.loads(row["proposal_flags_json"]),
                        batch_id=str(row["proposal_batch_id"]),
                    )
                    if row["proposed_pinyin"] is not None
                    else None
                ),
                stale_correction_fields=(
                    []
                    if row["correction_entry_id_at_review"] is None
                    else [
                        field
                        for field, differs in (
                            (
                                "entry_id_at_review",
                                row["correction_entry_id_at_review"] != row["entry_id"],
                            ),
                            (
                                "original_hanzi",
                                row["correction_original_hanzi"]
                                != row["current_hanzi_raw"],
                            ),
                            (
                                "original_pinyin",
                                row["correction_original_pinyin"]
                                != row["current_pinyin_raw"],
                            ),
                        )
                        if differs
                    ]
                ),
                correction_entry_id_at_review=(
                    int(row["correction_entry_id_at_review"])
                    if row["correction_entry_id_at_review"] is not None
                    else None
                ),
                correction_original_hanzi=row["correction_original_hanzi"],
                correction_original_pinyin=row["correction_original_pinyin"],
            )
            for row in rows
        ]

    def evidence_boxes(self, item: ReviewItem) -> list[sqlite3.Row]:
        return self.span_boxes(item.evidence_span_ids)

    def span_boxes(self, span_ids: Sequence[int]) -> list[sqlite3.Row]:
        if not span_ids:
            return []
        placeholders = ",".join("?" for _ in span_ids)
        return self.conn.execute(
            f"""
            SELECT id, text, confidence, page_number, column_number,
                   x1, y1, x2, y2
              FROM ocr_spans
             WHERE id IN ({placeholders})
             ORDER BY span_order
            """,
            span_ids,
        ).fetchall()

    @staticmethod
    def _looks_like_pinyin_only(text: str) -> bool:
        if any("\u3400" <= character <= "\u9fff" for character in text):
            return False
        if any(character.isdigit() for character in text):
            return False
        return any(
            "a" <= character.lower() <= "z"
            or unicodedata.category(character).startswith("M")
            for character in text
        )

    def _unassigned_spans(
        self,
        item: ReviewItem,
        *,
        page_number: int,
        column_number: int,
        minimum_y: float,
        maximum_y: float,
    ) -> list[sqlite3.Row]:
        rows = self.conn.execute(
            """
            SELECT s.id, s.text, s.confidence, s.x1, s.y1, s.x2, s.y2
              FROM ocr_spans AS s
             WHERE s.document_id=?
               AND s.page_number=?
               AND s.column_number=?
               AND s.y1>=?
               AND s.y1<=?
               AND NOT EXISTS (
                    SELECT 1
                      FROM entries AS assigned_entry,
                           json_each(assigned_entry.evidence_span_ids_json) AS evidence
                     WHERE assigned_entry.document_id=s.document_id
                       AND assigned_entry.page_number=s.page_number
                       AND CAST(evidence.value AS INTEGER)=s.id
               )
             ORDER BY s.y1, s.x1
            """,
            (
                item.document_id,
                page_number,
                column_number,
                minimum_y,
                maximum_y,
            ),
        ).fetchall()
        return [
            row for row in rows if self._looks_like_pinyin_only(str(row["text"]).strip())
        ]

    @staticmethod
    def _suggestion_from_rows(
        rows: Sequence[sqlite3.Row],
        *,
        source: str,
        page_number: int,
        column_number: int,
    ) -> ContinuationSuggestion | None:
        if not rows:
            return None
        fragments: list[str] = []
        previous_right: float | None = None
        for row in rows:
            text = str(row["text"]).strip()
            if previous_right is not None and float(row["x1"]) - previous_right > 8.0:
                fragments.append(" ")
            fragments.append(text)
            previous_right = float(row["x2"])
        return ContinuationSuggestion(
            text="".join(fragments),
            minimum_confidence=min(float(row["confidence"]) for row in rows),
            span_ids=[int(row["id"]) for row in rows],
            boxes=list(rows),
            source=source,
            page_number=page_number,
            column_number=column_number,
        )

    def continuation_suggestion(
        self, item: ReviewItem, evidence_boxes: Sequence[sqlite3.Row]
    ) -> ContinuationSuggestion | None:
        """Find an unassigned pinyin-only OCR continuation in reading order."""
        if item.pinyin or not evidence_boxes:
            return None
        evidence_bottom = max(float(row["y2"]) for row in evidence_boxes)
        candidates = self._unassigned_spans(
            item,
            page_number=item.page_number,
            column_number=item.column_number,
            minimum_y=evidence_bottom + 5.0,
            maximum_y=evidence_bottom + 18.0,
        )
        suggestion = self._suggestion_from_rows(
            candidates,
            source="ocr_same_column",
            page_number=item.page_number,
            column_number=item.column_number,
        )
        if suggestion:
            return suggestion

        # Some table rows end at the bottom of a column. Their pinyin is the
        # first unassigned line in the next column (or column 1 of the next
        # page). This is the missing boundary case behind 15 of the 317 batch
        # candidates in the supplied database.
        page = self.conn.execute(
            """
            SELECT image_height FROM pages
             WHERE document_id=? AND page_number=?
            """,
            (item.document_id, item.page_number),
        ).fetchone()
        image_height = float(page["image_height"] or 0) if page else 0.0
        if not image_height or evidence_bottom < image_height - 40.0:
            return None
        maximum_column = int(
            self.conn.execute(
                """
                SELECT COALESCE(MAX(column_number), 3) FROM entries
                 WHERE document_id=? AND table_number=?
                """,
                (item.document_id, item.table_number),
            ).fetchone()[0]
        )
        if item.column_number < maximum_column:
            next_page = item.page_number
            next_column = item.column_number + 1
            source = "ocr_next_column"
        else:
            next_page = item.page_number + 1
            next_column = 1
            source = "ocr_next_page"
        candidates = self._unassigned_spans(
            item,
            page_number=next_page,
            column_number=next_column,
            minimum_y=0.0,
            maximum_y=24.0,
        )
        if candidates:
            first_line_y = min(float(row["y1"]) for row in candidates)
            candidates = [
                row for row in candidates if float(row["y1"]) <= first_line_y + 6.0
            ]
        return self._suggestion_from_rows(
            candidates,
            source=source,
            page_number=next_page,
            column_number=next_column,
        )

    def _polyphonic_readings(self) -> dict[str, str]:
        """Return authoritative multi-reading characters already in this DB."""
        readings: dict[str, set[str]] = {}
        rows = self.conn.execute(
            """
            SELECT hanzi, pinyin_raw AS pinyin
              FROM entries
             WHERE length(trim(coalesce(hanzi, '')))=1
               AND trim(coalesce(pinyin_raw, ''))<>''
            UNION ALL
            SELECT corrected_hanzi AS hanzi, corrected_pinyin AS pinyin
              FROM manual_corrections
             WHERE length(trim(coalesce(corrected_hanzi, '')))=1
               AND decision IN ('corrected', 'confirmed')
               AND trim(coalesce(corrected_pinyin, ''))<>''
            """
        )
        for row in rows:
            value = str(row["pinyin"]).replace("\n", "").strip()
            alternatives = {part.strip() for part in value.split("/") if part.strip()}
            if len(alternatives) > 1:
                readings.setdefault(str(row["hanzi"]), set()).update(alternatives)
        return {character: "/".join(sorted(values)) for character, values in readings.items()}

    @staticmethod
    def _proposal_core(record: dict[str, Any]) -> dict[str, Any]:
        ignored = {"batch_id", "created_at_utc"}
        return {key: value for key, value in record.items() if key not in ignored}

    def prepare_pinyin_proposals(
        self,
        *,
        table_number: int = 2,
        minimum_hanzi_confidence: float = 0.85,
        uncertain_below: float = 0.98,
        persist: bool = True,
    ) -> dict[str, Any]:
        """Stage OCR-backed pinyin proposals without accepting any correction."""
        if persist and self.read_only:
            raise RuntimeError("cannot persist proposals through a read-only store")
        batch_id = "pinyin-" + utc_now().replace(":", "").replace("+", "_")
        polyphonic = self._polyphonic_readings()
        generated: list[dict[str, Any]] = []
        skipped = {
            "already_reviewed": 0,
            "outside_scope": 0,
            "low_hanzi_confidence": 0,
            "no_ocr_continuation": 0,
        }
        for item in self.load_items():
            if item.table_number != table_number or not item.hanzi or item.pinyin:
                skipped["outside_scope"] += 1
                continue
            if item.decision != "pending":
                skipped["already_reviewed"] += 1
                continue
            if (
                item.minimum_confidence is None
                or item.minimum_confidence < minimum_hanzi_confidence
            ):
                skipped["low_hanzi_confidence"] += 1
                continue
            suggestion = self.continuation_suggestion(item, self.evidence_boxes(item))
            if not suggestion:
                skipped["no_ocr_continuation"] += 1
                continue
            flags: list[str] = []
            for character in dict.fromkeys(item.hanzi):
                if character in polyphonic:
                    flags.append(f"多音字 {character}（{polyphonic[character]}）")
            if suggestion.minimum_confidence < uncertain_below:
                flags.append(
                    "拼音 OCR 置信度偏低"
                    f"（{suggestion.minimum_confidence:.3f} < {uncertain_below:.3f}）"
                )
            if "/" in suggestion.text:
                flags.append("建议中包含多个读音")
            if any(character.isspace() for character in suggestion.text):
                flags.append("拼音 OCR 分段含空格，请核对连接符")
            record = {
                "document_id": item.document_id,
                "table_number": item.table_number,
                "source_index": item.source_index,
                "entry_id_at_proposal": item.entry_id,
                "original_hanzi": item.hanzi,
                "original_pinyin": item.pinyin,
                "proposed_pinyin": suggestion.text,
                "source": suggestion.source,
                "minimum_confidence": suggestion.minimum_confidence,
                "evidence_span_ids_json": json.dumps(suggestion.span_ids),
                "review_class": "manual_review" if flags else "ready",
                "flags_json": json.dumps(flags, ensure_ascii=False),
                "batch_id": batch_id,
                "created_at_utc": utc_now(),
            }
            generated.append(record)

        counts = {"created": 0, "updated": 0, "unchanged": 0}
        if persist:
            with self.conn:
                for record in generated:
                    key = (
                        record["document_id"],
                        record["table_number"],
                        record["source_index"],
                    )
                    previous = self.conn.execute(
                        """
                        SELECT * FROM pinyin_proposals
                         WHERE document_id=? AND table_number=? AND source_index=?
                        """,
                        key,
                    ).fetchone()
                    previous_dict = dict(previous) if previous else None
                    if previous_dict and self._proposal_core(
                        previous_dict
                    ) == self._proposal_core(record):
                        counts["unchanged"] += 1
                        continue
                    action = "create" if previous is None else "update"
                    counts["created" if previous is None else "updated"] += 1
                    self.conn.execute(
                        """
                        INSERT INTO pinyin_proposals(
                            document_id, table_number, source_index,
                            entry_id_at_proposal, original_hanzi, original_pinyin,
                            proposed_pinyin, source, minimum_confidence,
                            evidence_span_ids_json, review_class, flags_json,
                            batch_id, created_at_utc
                        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(document_id, table_number, source_index) DO UPDATE SET
                            entry_id_at_proposal=excluded.entry_id_at_proposal,
                            original_hanzi=excluded.original_hanzi,
                            original_pinyin=excluded.original_pinyin,
                            proposed_pinyin=excluded.proposed_pinyin,
                            source=excluded.source,
                            minimum_confidence=excluded.minimum_confidence,
                            evidence_span_ids_json=excluded.evidence_span_ids_json,
                            review_class=excluded.review_class,
                            flags_json=excluded.flags_json,
                            batch_id=excluded.batch_id,
                            created_at_utc=excluded.created_at_utc
                        """,
                        tuple(record.values()),
                    )
                    self.conn.execute(
                        """
                        INSERT INTO pinyin_proposal_history(
                            document_id, table_number, source_index, action,
                            previous_json, current_json, occurred_at_utc
                        ) VALUES(?,?,?,?,?,?,?)
                        """,
                        (
                            *key,
                            action,
                            (
                                json.dumps(previous_dict, ensure_ascii=False)
                                if previous_dict
                                else None
                            ),
                            json.dumps(record, ensure_ascii=False),
                            utc_now(),
                        ),
                    )

        by_source: dict[str, int] = {}
        for record in generated:
            source = str(record["source"])
            by_source[source] = by_source.get(source, 0) + 1
        manual_review = sum(
            record["review_class"] == "manual_review" for record in generated
        )
        return {
            "database": str(self.database),
            "batch_id": batch_id,
            "persisted": persist,
            "table_number": table_number,
            "minimum_hanzi_confidence": minimum_hanzi_confidence,
            "uncertain_below": uncertain_below,
            "proposals": len(generated),
            "ready": len(generated) - manual_review,
            "manual_review": manual_review,
            "by_source": by_source,
            "changes": counts,
            "skipped": skipped,
        }

    def save(
        self,
        item: ReviewItem,
        decision: str,
        corrected_hanzi: str,
        corrected_pinyin: str,
        note: str,
        *,
        action: str = "save",
    ) -> None:
        if decision not in {"corrected", "confirmed", "unresolved"}:
            raise ValueError(f"unsupported decision: {decision}")
        previous = self.conn.execute(
            """
            SELECT * FROM manual_corrections
             WHERE document_id=? AND table_number=? AND source_index=?
            """,
            item.key,
        ).fetchone()
        current = {
            "entry_id_at_review": item.entry_id,
            "original_hanzi": item.hanzi,
            "original_pinyin": item.pinyin,
            "corrected_hanzi": corrected_hanzi,
            "corrected_pinyin": corrected_pinyin,
            "decision": decision,
            "review_note": note,
            "reviewer": "manual",
            "reviewed_at_utc": utc_now(),
        }
        previous_json = json.dumps(dict(previous), ensure_ascii=False) if previous else None
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO manual_corrections(
                    document_id, table_number, source_index, entry_id_at_review,
                    original_hanzi, original_pinyin, corrected_hanzi,
                    corrected_pinyin, decision, review_note, reviewer,
                    reviewed_at_utc
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(document_id, table_number, source_index) DO UPDATE SET
                    entry_id_at_review=excluded.entry_id_at_review,
                    original_hanzi=excluded.original_hanzi,
                    original_pinyin=excluded.original_pinyin,
                    corrected_hanzi=excluded.corrected_hanzi,
                    corrected_pinyin=excluded.corrected_pinyin,
                    decision=excluded.decision,
                    review_note=excluded.review_note,
                    reviewer=excluded.reviewer,
                    reviewed_at_utc=excluded.reviewed_at_utc
                """,
                (
                    item.document_id,
                    item.table_number,
                    item.source_index,
                    current["entry_id_at_review"],
                    current["original_hanzi"],
                    current["original_pinyin"],
                    current["corrected_hanzi"],
                    current["corrected_pinyin"],
                    current["decision"],
                    current["review_note"],
                    current["reviewer"],
                    current["reviewed_at_utc"],
                ),
            )
            self.conn.execute(
                """
                INSERT INTO manual_review_history(
                    document_id, table_number, source_index, action,
                    previous_json, current_json, occurred_at_utc
                ) VALUES(?,?,?,?,?,?,?)
                """,
                (
                    item.document_id,
                    item.table_number,
                    item.source_index,
                    action,
                    previous_json,
                    json.dumps(current, ensure_ascii=False),
                    utc_now(),
                ),
            )

    def clear(self, item: ReviewItem) -> None:
        previous = self.conn.execute(
            """
            SELECT * FROM manual_corrections
             WHERE document_id=? AND table_number=? AND source_index=?
            """,
            item.key,
        ).fetchone()
        if not previous:
            return
        with self.conn:
            self.conn.execute(
                """
                DELETE FROM manual_corrections
                 WHERE document_id=? AND table_number=? AND source_index=?
                """,
                item.key,
            )
            self.conn.execute(
                """
                INSERT INTO manual_review_history(
                    document_id, table_number, source_index, action,
                    previous_json, current_json, occurred_at_utc
                ) VALUES(?,?,?,?,?,NULL,?)
                """,
                (
                    item.document_id,
                    item.table_number,
                    item.source_index,
                    "clear",
                    json.dumps(dict(previous), ensure_ascii=False),
                    utc_now(),
                ),
            )

    def stats(self) -> dict[str, int]:
        result = {key: 0 for key in DECISION_LABELS}
        result["proposals"] = 0
        result["proposal_manual_review"] = 0
        result["stale_corrections"] = 0
        result["pending"] = int(
            self.conn.execute(
                """
                SELECT COUNT(*)
                  FROM entries AS e
                  LEFT JOIN manual_corrections AS c
                    ON c.document_id=e.document_id
                   AND c.table_number=e.table_number
                   AND c.source_index=e.source_index
                 WHERE e.status='needs_review' AND c.decision IS NULL
                """
            ).fetchone()[0]
        )
        for row in self.conn.execute(
            "SELECT decision, COUNT(*) AS count FROM manual_corrections GROUP BY decision"
        ):
            result[str(row["decision"])] = int(row["count"])
        result["stale_corrections"] = int(
            self.conn.execute(
                """
                SELECT COUNT(*)
                  FROM manual_corrections AS c
                  LEFT JOIN entries AS e
                    ON e.document_id=c.document_id
                   AND e.table_number=c.table_number
                   AND e.source_index=c.source_index
                 WHERE e.id IS NULL
                    OR c.entry_id_at_review IS NOT e.id
                    OR c.original_hanzi IS NOT e.hanzi
                    OR c.original_pinyin IS NOT e.pinyin_raw
                """
            ).fetchone()[0]
        )
        if self._table_exists("pinyin_proposals"):
            proposal_counts = self.conn.execute(
                """
                SELECT COUNT(*) AS total,
                       COALESCE(SUM(pr.review_class='manual_review'), 0) AS flagged
                  FROM pinyin_proposals AS pr
                  JOIN entries AS e
                    ON e.document_id=pr.document_id
                   AND e.table_number=pr.table_number
                   AND e.source_index=pr.source_index
                  LEFT JOIN manual_corrections AS c
                    ON c.document_id=e.document_id
                   AND c.table_number=e.table_number
                   AND c.source_index=e.source_index
                 WHERE e.status='needs_review' AND c.decision IS NULL
                """
            ).fetchone()
            result["proposals"] = int(proposal_counts["total"])
            result["proposal_manual_review"] = int(proposal_counts["flagged"])
        return result


def format_manual_correction_validation_report(report: dict[str, Any]) -> str:
    """Render a compact human-readable form of the read-only JSON report."""
    lines = [
        f"共检查 {report['checked_corrections']} 条人工校对；"
        f"有效 {report['valid_corrections']} 条，过期 {report['stale_corrections']} 条。",
        "",
    ]
    for mismatch in report["mismatches"]:
        key = (
            f"表{mismatch['table_number']}-{mismatch['source_index']}"
            f"（文档 {mismatch['document_id']}）"
        )
        labels = "、".join(
            STALE_CORRECTION_FIELD_LABELS[field]
            for field in mismatch["mismatched_fields"]
        )
        lines.append(f"{key}：{labels}")
        stored = mismatch["stored"]
        current = mismatch["current"]
        lines.append(
            "  复核时："
            f"entry_id={stored['entry_id']!r}，"
            f"汉字={stored['original_hanzi']!r}，"
            f"拼音={stored['original_pinyin']!r}"
        )
        if current is None:
            lines.append("  当前：找不到相同文档/表号/序号的条目")
        else:
            lines.append(
                "  当前："
                f"entry_id={current['entry_id']!r}，"
                f"汉字={current['hanzi']!r}，"
                f"拼音={current['pinyin']!r}"
            )
        lines.append("")
    return "\n".join(lines).rstrip()


def resolve_image_path(item: ReviewItem, database: Path, image_dir: Path | None) -> Path:
    candidates: list[Path] = []
    if image_dir:
        candidates.append(image_dir / f"page-{item.page_number:04d}.png")
    if item.image_path:
        candidates.append(Path(item.image_path))
    candidates.append(database.parent / "pages" / f"page-{item.page_number:04d}.png")
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return candidates[0] if candidates else Path(item.image_path)


def create_review_crop(
    image_path: Path,
    column_number: int,
    evidence_boxes: Sequence[sqlite3.Row],
    continuation_boxes: Sequence[sqlite3.Row] = (),
    maximum_size: tuple[int, int] = (1000, 300),
) -> Any:
    from PIL import Image, ImageDraw

    image = Image.open(image_path).convert("RGBA")
    width, height = image.size
    all_boxes = list(evidence_boxes) + list(continuation_boxes)
    if all_boxes:
        y1 = min(float(row["y1"]) for row in all_boxes)
        y2 = max(float(row["y2"]) for row in all_boxes)
        center_y = (y1 + y2) / 2.0
    else:
        center_y = height / 2.0
    column_width = width / 3.0
    crop_left = max(0, int((column_number - 1) * column_width - 30))
    crop_right = min(width, int(column_number * column_width + 30))
    crop_top = max(0, int(center_y - 100))
    crop_bottom = min(height, int(center_y + 100))

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rectangle(
        (crop_left, max(0, int(center_y - 28)), crop_right, min(height, int(center_y + 28))),
        fill=(255, 230, 80, 45),
        outline=(230, 170, 0, 180),
        width=2,
    )
    for row in evidence_boxes:
        draw.rectangle(
            (float(row["x1"]), float(row["y1"]), float(row["x2"]), float(row["y2"])),
            outline=(220, 35, 35, 255),
            width=3,
        )
    for row in continuation_boxes:
        draw.rectangle(
            (float(row["x1"]), float(row["y1"]), float(row["x2"]), float(row["y2"])),
            outline=(25, 105, 210, 255),
            width=3,
        )
    marked = Image.alpha_composite(image, overlay).crop(
        (crop_left, crop_top, crop_right, crop_bottom)
    ).convert("RGB")
    scale = min(maximum_size[0] / marked.width, maximum_size[1] / marked.height, 2.5)
    target = (max(1, round(marked.width * scale)), max(1, round(marked.height * scale)))
    return marked.resize(target, Image.Resampling.LANCZOS)


class ReviewApplication:
    def __init__(self, store: ReviewStore, image_dir: Path | None) -> None:
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.ttk = ttk
        self.store = store
        self.database = store.database
        self.image_dir = image_dir.resolve() if image_dir else None
        self.all_items = store.load_items()
        self.items: list[ReviewItem] = []
        self.position = 0
        self.current_photo = None
        self.current_image_path: Path | None = None
        self.current_suggestion: ContinuationSuggestion | None = None

        self.root = tk.Tk()
        self.root.title("普通话纲要 OCR 校对")
        self.root.geometry("1120x760")
        self.root.minsize(900, 650)
        self.root.option_add("*Font", ("Microsoft YaHei UI", 11))
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 16, "bold"))
        style.configure("Value.TEntry", font=("Microsoft YaHei UI", 16))

        self.filter_var = tk.StringVar(value="待处理")
        self.location_var = tk.StringVar()
        self.progress_var = tk.StringVar()
        self.metadata_var = tk.StringVar()
        self.hanzi_var = tk.StringVar()
        self.pinyin_var = tk.StringVar()
        self.search_var = tk.StringVar()
        self.suggestion_var = tk.StringVar()
        self.validation_var = tk.StringVar()

        self._build_ui()
        self._bind_keys()
        self.apply_filter(select_key=None)

    def _build_ui(self) -> None:
        tk, ttk = self.tk, self.ttk
        top = ttk.Frame(self.root, padding=(12, 10))
        top.pack(fill="x")
        ttk.Label(top, text="普通话纲要 OCR 校对", style="Title.TLabel").pack(side="left")
        ttk.Label(top, textvariable=self.progress_var).pack(side="right")

        controls = ttk.Frame(self.root, padding=(12, 0, 12, 8))
        controls.pack(fill="x")
        ttk.Label(controls, text="显示：").pack(side="left")
        filter_box = ttk.Combobox(
            controls,
            textvariable=self.filter_var,
            values=(
                "待处理",
                "有批量建议",
                "建议需重点复核",
                "已接受建议",
                "已过期校对",
                "全部",
                "已修改",
                "确认无误",
                "暂无法判断",
            ),
            state="readonly",
            width=12,
        )
        filter_box.pack(side="left")
        filter_box.bind("<<ComboboxSelected>>", lambda _event: self.apply_filter(None))
        ttk.Label(controls, text="跳转（如 1-248）：").pack(side="left", padx=(20, 4))
        search_entry = ttk.Entry(controls, textvariable=self.search_var, width=14)
        search_entry.pack(side="left")
        search_entry.bind("<Return>", lambda _event: self.jump_to())
        ttk.Button(controls, text="跳转", command=self.jump_to).pack(side="left", padx=4)
        ttk.Button(controls, text="打开整页", command=self.open_full_page).pack(side="right")
        ttk.Button(
            controls, text="查看校验报告", command=self.show_validation_report
        ).pack(side="right", padx=6)
        ttk.Button(
            controls, text="生成批量拼音建议", command=self.prepare_proposals
        ).pack(side="right")

        location = ttk.Frame(self.root, padding=(12, 2, 12, 8))
        location.pack(fill="x")
        ttk.Label(location, textvariable=self.location_var, style="Title.TLabel").pack(side="left")
        ttk.Label(location, textvariable=self.metadata_var).pack(side="right")

        self.suggestion_label = tk.Label(
            self.root,
            textvariable=self.suggestion_var,
            anchor="w",
            fg="#005a9c",
            font=("Microsoft YaHei UI", 11, "bold"),
            padx=12,
            pady=2,
        )
        self.suggestion_label.pack(fill="x")

        self.validation_label = tk.Label(
            self.root,
            textvariable=self.validation_var,
            anchor="w",
            fg="#b42318",
            font=("Microsoft YaHei UI", 11, "bold"),
            padx=12,
            pady=2,
        )
        self.validation_label.pack(fill="x")

        image_frame = ttk.LabelFrame(
            self.root,
            text="原始 PNG 局部（黄色为所在行，红框为原证据，蓝框为检测到的换行拼音）",
            padding=8,
        )
        image_frame.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        self.image_label = ttk.Label(image_frame, anchor="center")
        self.image_label.pack(fill="both", expand=True)

        form = ttk.Frame(self.root, padding=(12, 0, 12, 6))
        form.pack(fill="x")
        ttk.Label(form, text="汉字：", width=8).grid(row=0, column=0, sticky="w", pady=4)
        self.hanzi_entry = ttk.Entry(form, textvariable=self.hanzi_var, style="Value.TEntry")
        self.hanzi_entry.grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Label(form, text="拼音：", width=8).grid(row=1, column=0, sticky="w", pady=4)
        self.pinyin_entry = ttk.Entry(form, textvariable=self.pinyin_var, style="Value.TEntry")
        self.pinyin_entry.grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Label(form, text="问题：", width=8).grid(row=2, column=0, sticky="nw", pady=4)
        self.issue_text = tk.Text(form, height=3, wrap="word", font=("Microsoft YaHei UI", 10))
        self.issue_text.grid(row=2, column=1, sticky="ew", pady=4)
        ttk.Label(form, text="备注：", width=8).grid(row=3, column=0, sticky="nw", pady=4)
        self.note_text = tk.Text(form, height=2, wrap="word", font=("Microsoft YaHei UI", 10))
        self.note_text.grid(row=3, column=1, sticky="ew", pady=4)
        form.columnconfigure(1, weight=1)

        buttons = ttk.Frame(self.root, padding=(12, 4, 12, 12))
        buttons.pack(fill="x")
        ttk.Button(buttons, text="◀ 上一条", command=self.previous).pack(side="left")
        ttk.Button(buttons, text="下一条 ▶", command=self.next).pack(side="left", padx=6)
        ttk.Button(buttons, text="撤销本条校对", command=self.clear_current).pack(side="left", padx=(14, 0))
        ttk.Button(buttons, text="暂无法判断", command=self.mark_unresolved).pack(side="right")
        ttk.Button(buttons, text="确认无误并下一条", command=self.confirm_and_next).pack(side="right", padx=6)
        ttk.Button(buttons, text="保存修改并下一条", command=self.save_and_next).pack(side="right")
        self.accept_proposal_button = ttk.Button(
            buttons,
            text="接受批量建议并下一条",
            command=self.accept_proposal_and_next,
        )
        self.accept_proposal_button.pack(side="right", padx=6)

    def _bind_keys(self) -> None:
        self.root.bind("<F7>", lambda _event: self.previous())
        self.root.bind("<F8>", lambda _event: self.next())
        self.root.bind("<Control-Return>", lambda _event: self.save_and_next())
        self.root.bind("<Control-Shift-Return>", lambda _event: self.confirm_and_next())

    def decision_for_filter(self) -> str | None:
        mapping = {
            "待处理": "pending",
            "有批量建议": "proposal",
            "建议需重点复核": "proposal_manual_review",
            "已接受建议": "accepted_proposal",
            "已过期校对": "stale_correction",
            "全部": None,
            "已修改": "corrected",
            "确认无误": "confirmed",
            "暂无法判断": "unresolved",
        }
        return mapping[self.filter_var.get()]

    @staticmethod
    def _matches_filter(item: ReviewItem, decision: str | None) -> bool:
        if decision == "proposal":
            return item.decision == "pending" and item.proposal is not None
        if decision == "proposal_manual_review":
            return (
                item.decision == "pending"
                and item.proposal is not None
                and item.proposal.review_class == "manual_review"
            )
        if decision == "accepted_proposal":
            return item.decision == "corrected" and item.proposal is not None
        if decision == "stale_correction":
            return item.has_stale_correction
        return decision is None or item.decision == decision

    def apply_filter(self, select_key: tuple[int, int, int] | None) -> None:
        self.all_items = self.store.load_items()
        decision = self.decision_for_filter()
        self.items = [
            item for item in self.all_items if self._matches_filter(item, decision)
        ]
        self.position = 0
        if select_key:
            for index, item in enumerate(self.items):
                if item.key == select_key:
                    self.position = index
                    break
        self.show_current()

    def current(self) -> ReviewItem | None:
        if not self.items:
            return None
        return self.items[self.position]

    def show_current(self) -> None:
        item = self.current()
        stats = self.store.stats()
        self.progress_var.set(
            f"待处理 {stats['pending']} / 已修改 {stats['corrected']} / "
            f"确认 {stats['confirmed']} / 未决 {stats['unresolved']} / "
            f"建议 {stats['proposals']}（重点 {stats['proposal_manual_review']}） / "
            f"过期 {stats['stale_corrections']}"
        )
        if not item:
            self.location_var.set("当前筛选条件下没有记录")
            self.metadata_var.set("")
            self.hanzi_var.set("")
            self.pinyin_var.set("")
            self.suggestion_var.set("")
            self.validation_var.set("")
            self.current_suggestion = None
            self.accept_proposal_button.configure(state="disabled")
            self.image_label.configure(image="", text="没有待显示的记录")
            return

        if item.has_stale_correction:
            details: list[str] = []
            if "entry_id_at_review" in item.stale_correction_fields:
                details.append(
                    "条目 ID "
                    f"{item.correction_entry_id_at_review!r} → {item.entry_id!r}"
                )
            if "original_hanzi" in item.stale_correction_fields:
                details.append(
                    "原汉字 "
                    f"{item.correction_original_hanzi!r} → {item.hanzi!r}"
                )
            if "original_pinyin" in item.stale_correction_fields:
                details.append(
                    "原拼音 "
                    f"{item.correction_original_pinyin!r} → {item.pinyin!r}"
                )
            self.validation_var.set(
                "⚠ 此校对已被最新重解析判定为过期：" + "；".join(details)
            )
        else:
            self.validation_var.set("")

        self.location_var.set(
            f"表{item.table_number} · 第 {item.source_index} 条 · "
            f"PDF 第 {item.page_number} 页 · 第 {item.column_number} 栏"
        )
        confidence = "—" if item.minimum_confidence is None else f"{item.minimum_confidence:.3f}"
        self.metadata_var.set(
            f"{self.position + 1}/{len(self.items)}　"
            f"状态：{DECISION_LABELS[item.decision]}　最低置信度：{confidence}"
        )
        evidence_boxes = self.store.evidence_boxes(item)
        if item.proposal:
            proposal_boxes = self.store.span_boxes(item.proposal.span_ids)
            first_box = proposal_boxes[0] if proposal_boxes else None
            self.current_suggestion = ContinuationSuggestion(
                text=item.proposal.text,
                minimum_confidence=item.proposal.minimum_confidence,
                span_ids=item.proposal.span_ids,
                boxes=proposal_boxes,
                source=item.proposal.source,
                page_number=(int(first_box["page_number"]) if first_box else None),
                column_number=(int(first_box["column_number"]) if first_box else None),
            )
        else:
            self.current_suggestion = self.store.continuation_suggestion(item, evidence_boxes)
        self.hanzi_var.set(item.corrected_hanzi)
        suggested_pinyin = (
            self.current_suggestion.text
            if self.current_suggestion and not item.corrected_pinyin and item.decision == "pending"
            else item.corrected_pinyin
        )
        self.pinyin_var.set(suggested_pinyin)
        if item.proposal:
            source_label = PROPOSAL_SOURCE_LABELS.get(
                item.proposal.source, item.proposal.source
            )
            flags = "；".join(item.proposal.flags) if item.proposal.flags else "无风险标记"
            self.suggestion_var.set(
                f"{PROPOSAL_LABELS[item.proposal.review_class]}：{item.proposal.text}　"
                f"来源：{source_label}　置信度：{item.proposal.minimum_confidence:.3f}　"
                f"{flags}"
            )
            self.suggestion_label.configure(
                fg="#a33a00" if item.proposal.review_class == "manual_review" else "#005a9c"
            )
            self.accept_proposal_button.configure(
                state="normal" if item.decision == "pending" else "disabled"
            )
        elif self.current_suggestion:
            self.suggestion_var.set(
                "检测到尚未批量暂存的换行拼音，已预填："
                f"{self.current_suggestion.text}　"
                f"（最低置信度 {self.current_suggestion.minimum_confidence:.3f}，蓝框）"
            )
            self.suggestion_label.configure(fg="#005a9c")
            self.accept_proposal_button.configure(state="disabled")
        else:
            self.suggestion_var.set("")
            self.accept_proposal_button.configure(state="disabled")
        self.note_text.delete("1.0", "end")
        self.note_text.insert("1.0", item.review_note)
        self.issue_text.configure(state="normal")
        self.issue_text.delete("1.0", "end")
        self.issue_text.insert(
            "1.0",
            f"OCR 原文：{item.raw_text or '（空）'}\n{item.issue_summary}",
        )
        self.issue_text.configure(state="disabled")
        self._show_image(item, evidence_boxes)
        self.hanzi_entry.focus_set()
        self.hanzi_entry.selection_range(0, "end")

    def _show_image(
        self, item: ReviewItem, evidence_boxes: Sequence[sqlite3.Row] | None = None
    ) -> None:
        from PIL import ImageTk

        path = resolve_image_path(item, self.database, self.image_dir)
        self.current_image_path = path
        if not path.is_file():
            self.current_photo = None
            self.image_label.configure(
                image="", text=f"找不到第 {item.page_number} 页 PNG：\n{path}"
            )
            return
        try:
            crop = create_review_crop(
                path,
                item.column_number,
                evidence_boxes if evidence_boxes is not None else self.store.evidence_boxes(item),
                (
                    self.current_suggestion.boxes
                    if self.current_suggestion
                    and self.current_suggestion.page_number == item.page_number
                    and self.current_suggestion.column_number == item.column_number
                    else ()
                ),
            )
            self.current_photo = ImageTk.PhotoImage(crop)
            self.image_label.configure(image=self.current_photo, text="")
        except Exception as error:
            self.current_photo = None
            self.image_label.configure(image="", text=f"图片加载失败：{error}")

    def _values(self) -> tuple[str, str, str]:
        hanzi = self.hanzi_var.get().strip()
        pinyin = self.pinyin_var.get().strip()
        note = self.note_text.get("1.0", "end").strip()
        item = self.current()
        if (
            item
            and item.proposal
            and pinyin == item.proposal.text
            and not note
        ):
            note = (
                "采用批量拼音建议；batch_id="
                + item.proposal.batch_id
                + "；source="
                + item.proposal.source
                + "；OCR span_ids="
                + ",".join(str(value) for value in item.proposal.span_ids)
            )
            if item.proposal.flags:
                note += "；复核标记=" + "；".join(item.proposal.flags)
        elif (
            self.current_suggestion
            and pinyin == self.current_suggestion.text
            and not note
        ):
            note = (
                "采用工具检测的换行拼音；OCR span_ids="
                + ",".join(str(value) for value in self.current_suggestion.span_ids)
            )
        return hanzi, pinyin, note

    def _save_decision(self, decision: str, *, action: str = "save") -> bool:
        from tkinter import messagebox

        item = self.current()
        if not item:
            return False
        hanzi, pinyin, note = self._values()
        if decision in {"corrected", "confirmed"} and (not hanzi or not pinyin):
            messagebox.showwarning("内容未完整", "汉字和拼音都填写后才能保存或确认。")
            return False
        if decision == "confirmed" and (hanzi != item.hanzi or pinyin != item.pinyin):
            messagebox.showinfo(
                "内容已有变化",
                "当前内容与 OCR 原值不同；请使用“保存修改并下一条”。",
            )
            return False
        if decision == "corrected" and hanzi == item.hanzi and pinyin == item.pinyin:
            messagebox.showinfo("没有修改", "内容与 OCR 原值相同；如原值正确，请使用“确认无误”。")
            return False
        self.store.save(item, decision, hanzi, pinyin, note, action=action)
        return True

    def save_and_next(self) -> None:
        if self._save_decision("corrected"):
            self._after_save()

    def accept_proposal_and_next(self) -> None:
        from tkinter import messagebox

        item = self.current()
        if not item or not item.proposal:
            return
        if self.pinyin_var.get().strip() != item.proposal.text:
            messagebox.showinfo(
                "建议已被编辑",
                "当前拼音与批量建议不同；请使用“保存修改并下一条”保留你的编辑。",
            )
            return
        if self._save_decision("corrected", action="accept_pinyin_proposal"):
            self._after_save()

    def confirm_and_next(self) -> None:
        if self._save_decision("confirmed"):
            self._after_save()

    def mark_unresolved(self) -> None:
        if self._save_decision("unresolved"):
            self._after_save()

    def _after_save(self) -> None:
        current_position = self.position
        self.all_items = self.store.load_items()
        decision = self.decision_for_filter()
        self.items = [
            item for item in self.all_items if self._matches_filter(item, decision)
        ]
        if self.items:
            self.position = min(current_position, len(self.items) - 1)
        else:
            self.position = 0
        self.show_current()

    def clear_current(self) -> None:
        from tkinter import messagebox

        item = self.current()
        if not item or item.decision == "pending":
            return
        if not messagebox.askyesno("撤销校对", "撤销本条人工校对，使其重新进入待处理队列？"):
            return
        self.store.clear(item)
        self.apply_filter(select_key=item.key)

    def previous(self) -> None:
        if self.items:
            self.position = (self.position - 1) % len(self.items)
            self.show_current()

    def next(self) -> None:
        if self.items:
            self.position = (self.position + 1) % len(self.items)
            self.show_current()

    def jump_to(self) -> None:
        from tkinter import messagebox

        value = self.search_var.get().strip().replace("：", "-").replace(":", "-")
        try:
            table_text, index_text = value.split("-", 1)
            table_number, source_index = int(table_text), int(index_text)
        except ValueError:
            messagebox.showwarning("格式不正确", "请输入“表号-序号”，例如：1-248。")
            return
        self.filter_var.set("全部")
        self.apply_filter(None)
        for position, item in enumerate(self.items):
            if item.table_number == table_number and item.source_index == source_index:
                self.position = position
                self.show_current()
                return
        messagebox.showinfo("未找到", "这个编号不在待复核条目中。")

    def prepare_proposals(self) -> None:
        from tkinter import messagebox

        try:
            summary = self.store.prepare_pinyin_proposals()
        except Exception as error:
            messagebox.showerror("生成失败", str(error))
            return
        self.filter_var.set("有批量建议")
        self.apply_filter(None)
        messagebox.showinfo(
            "批量建议已暂存",
            "未改动 OCR 原表，也未自动接受任何校对。\n"
            f"建议 {summary['proposals']} 条：可复核 {summary['ready']} 条，"
            f"需重点复核 {summary['manual_review']} 条。\n"
            f"新建 {summary['changes']['created']} 条，更新 "
            f"{summary['changes']['updated']} 条，未变化 "
            f"{summary['changes']['unchanged']} 条。",
        )

    def show_validation_report(self) -> None:
        from tkinter import scrolledtext

        report = self.store.manual_correction_validation_report()
        window = self.tk.Toplevel(self.root)
        window.title("人工校对重解析校验报告（只读）")
        window.geometry("900x560")
        window.minsize(700, 400)
        summary = (
            f"检查 {report['checked_corrections']} 条 · "
            f"有效 {report['valid_corrections']} 条 · "
            f"过期 {report['stale_corrections']} 条 · "
            f"当前条目缺失 {report['missing_entries']} 条"
        )
        self.ttk.Label(
            window,
            text=summary,
            style="Title.TLabel",
            padding=(12, 12, 12, 8),
        ).pack(fill="x")
        self.ttk.Label(
            window,
            text="本报告只查询数据库，不会更新人工校对或 OCR 数据。",
            padding=(12, 0, 12, 8),
        ).pack(fill="x")
        report_text = scrolledtext.ScrolledText(
            window, wrap="word", font=("Microsoft YaHei UI", 10), padx=8, pady=8
        )
        report_text.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        report_text.insert("1.0", format_manual_correction_validation_report(report))
        report_text.configure(state="disabled")

    def open_full_page(self) -> None:
        from tkinter import messagebox

        if not self.current_image_path or not self.current_image_path.is_file():
            messagebox.showwarning("找不到图片", "当前记录没有可用的 PNG 页面。")
            return
        os.startfile(self.current_image_path)  # type: ignore[attr-defined]

    def close(self) -> None:
        self.store.close()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def run_self_test(database: Path, image_dir: Path | None) -> int:
    store = ReviewStore(database)
    try:
        items = store.load_items()
        if not items:
            raise RuntimeError("database contains no entries needing review")
        item = items[0]
        evidence_boxes = store.evidence_boxes(item)
        suggestion = store.continuation_suggestion(item, evidence_boxes)
        for candidate in items:
            if candidate.decision != "pending":
                continue
            candidate_boxes = store.evidence_boxes(candidate)
            candidate_suggestion = store.continuation_suggestion(candidate, candidate_boxes)
            if candidate_suggestion:
                item = candidate
                evidence_boxes = candidate_boxes
                suggestion = candidate_suggestion
                break
        if not suggestion:
            raise RuntimeError("database contains no detectable wrapped-pinyin example")
        before_entries = store.conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
        original = (item.hanzi, item.pinyin)
        test_hanzi = item.hanzi or "挨"
        test_pinyin = suggestion.text
        store.save(item, "corrected", test_hanzi, test_pinyin, "automated self-test")
        saved = store.conn.execute(
            """
            SELECT decision, corrected_hanzi, corrected_pinyin
              FROM manual_corrections
             WHERE document_id=? AND table_number=? AND source_index=?
            """,
            item.key,
        ).fetchone()
        assert saved and saved["decision"] == "corrected"
        assert (saved["corrected_hanzi"], saved["corrected_pinyin"]) == (
            test_hanzi,
            test_pinyin,
        )
        assert store.conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0] == before_entries
        path = resolve_image_path(item, database, image_dir)
        crop = create_review_crop(
            path,
            item.column_number,
            evidence_boxes,
            suggestion.boxes if suggestion else (),
        )
        assert crop.width > 0 and crop.height > 0
        store.clear(item)
        assert (
            store.conn.execute(
                """
                SELECT COUNT(*) FROM manual_corrections
                 WHERE document_id=? AND table_number=? AND source_index=?
                """,
                item.key,
            ).fetchone()[0]
            == 0
        )
        print(
            json.dumps(
                {
                    "database": str(database.resolve()),
                    "queue_entries": len(items),
                    "tested_entry": f"{item.table_number}-{item.source_index}",
                    "original": original,
                    "image": str(path),
                    "crop_size": crop.size,
                    "continuation_suggestion": suggestion.text if suggestion else None,
                    "entries_unchanged": True,
                    "result": "ok",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    finally:
        store.close()


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "database",
        nargs="?",
        type=Path,
        default=Path(__file__).resolve().with_name("psc_outline_ocr.sqlite3"),
    )
    parser.add_argument("--image-dir", type=Path)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument(
        "--validate-manual-corrections",
        "--validate-corrections",
        action="store_true",
        help="print a read-only stale manual-correction report, then exit",
    )
    proposal_mode = parser.add_mutually_exclusive_group()
    proposal_mode.add_argument(
        "--prepare-pinyin-proposals",
        action="store_true",
        help="stage OCR-backed pinyin proposals, then exit",
    )
    proposal_mode.add_argument(
        "--preview-pinyin-proposals",
        action="store_true",
        help="report proposals without writing schema or data",
    )
    parser.add_argument("--proposal-table", type=int, default=2)
    parser.add_argument("--minimum-hanzi-confidence", type=float, default=0.85)
    parser.add_argument("--uncertain-below", type=float, default=0.98)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    database = args.database.resolve()
    if not database.is_file():
        print(f"database not found: {database}", file=sys.stderr)
        return 2
    image_dir = args.image_dir.resolve() if args.image_dir else None
    if args.validate_manual_corrections:
        store = ReviewStore(database, read_only=True)
        try:
            report = store.manual_correction_validation_report()
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0
        finally:
            store.close()
    if args.self_test:
        return run_self_test(database, image_dir)
    if args.prepare_pinyin_proposals or args.preview_pinyin_proposals:
        store = ReviewStore(database, read_only=args.preview_pinyin_proposals)
        try:
            summary = store.prepare_pinyin_proposals(
                table_number=args.proposal_table,
                minimum_hanzi_confidence=args.minimum_hanzi_confidence,
                uncertain_below=args.uncertain_below,
                persist=args.prepare_pinyin_proposals,
            )
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0
        finally:
            store.close()
    store = ReviewStore(database)
    application = ReviewApplication(store, image_dir)
    application.run()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as error:
        try:
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("校对工具无法启动", f"{type(error).__name__}: {error}")
            root.destroy()
        finally:
            raise
