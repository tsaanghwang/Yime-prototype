"""SQLite decision overlay for input candidate organization."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .types import (
    CandidateAssessment,
    CandidateClass,
    ContextEvidence,
    DecisionStatus,
    IntegrationPolicy,
)


SCHEMA_VERSION = "yime-input-candidate-model-v1"


SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS assessments (
    text TEXT PRIMARY KEY,
    text_length INTEGER NOT NULL,
    bcc_frequency INTEGER NOT NULL,
    candidate_class TEXT NOT NULL,
    integration_policy TEXT NOT NULL,
    decision_status TEXT NOT NULL,
    confidence REAL,
    rationale TEXT NOT NULL,
    assessor TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    allowed_reading_ids_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS assessment_review_idx
    ON assessments(decision_status, bcc_frequency DESC, integration_policy, candidate_class, text);
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    event_type TEXT NOT NULL,
    assessor TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS context_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    left_context TEXT NOT NULL,
    matched_text TEXT NOT NULL,
    right_context TEXT NOT NULL,
    source TEXT NOT NULL,
    source_reference TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    UNIQUE(text, left_context, matched_text, right_context, source, source_reference)
);
CREATE INDEX IF NOT EXISTS context_evidence_text_idx
    ON context_evidence(text, source, id);
CREATE TABLE IF NOT EXISTS composition_patterns (
    pattern_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    minimum_parts INTEGER NOT NULL,
    maximum_parts INTEGER NOT NULL,
    rationale TEXT NOT NULL,
    evidence_json TEXT NOT NULL
) WITHOUT ROWID;
CREATE VIEW IF NOT EXISTS v_review_queue AS
SELECT text, text_length, bcc_frequency, candidate_class, integration_policy,
       confidence, rationale, assessor, evidence_json, updated_at_utc
FROM assessments
WHERE decision_status IN ('proposed', 'deferred');
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class InputModelStore:
    """Persist decisions without modifying the source lexicon."""

    def __init__(self, database: Path):
        self.database = database.resolve()
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.database)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(SCHEMA)

    def initialize(self, *, source_database: Path, policy_path: Path) -> None:
        source = str(source_database.resolve())
        policy = str(policy_path.resolve())
        existing = dict(self.connection.execute("SELECT key, value FROM metadata"))
        if existing.get("source_database") not in {None, source}:
            raise ValueError(
                "input model is already bound to another source database: "
                + existing["source_database"]
            )
        values = {
            "schema_version": SCHEMA_VERSION,
            "source_database": source,
            "policy_path": policy,
        }
        self.connection.executemany(
            """
            INSERT INTO metadata(key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            values.items(),
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "InputModelStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def get(self, text: str) -> CandidateAssessment | None:
        row = self.connection.execute(
            "SELECT * FROM assessments WHERE text = ?",
            (text,),
        ).fetchone()
        if row is None:
            return None
        return CandidateAssessment(
            text=str(row["text"]),
            candidate_class=CandidateClass(row["candidate_class"]),
            integration_policy=IntegrationPolicy(row["integration_policy"]),
            status=DecisionStatus(row["decision_status"]),
            confidence=float(row["confidence"]) if row["confidence"] is not None else None,
            rationale=str(row["rationale"]),
            assessor=str(row["assessor"]),
            evidence=json.loads(row["evidence_json"]),
            allowed_reading_ids=tuple(json.loads(row["allowed_reading_ids_json"])),
        )

    def put(self, assessment: CandidateAssessment, *, overwrite: bool = True) -> bool:
        current = self.get(assessment.text)
        if current is not None and not overwrite:
            return False
        now = _now()
        created = now
        if current is not None:
            row = self.connection.execute(
                "SELECT created_at_utc FROM assessments WHERE text = ?",
                (assessment.text,),
            ).fetchone()
            created = str(row[0])
        payload = {
            "candidate_class": assessment.candidate_class.value,
            "integration_policy": assessment.integration_policy.value,
            "decision_status": assessment.status.value,
            "confidence": assessment.confidence,
            "rationale": assessment.rationale,
            "evidence": assessment.evidence,
            "allowed_reading_ids": assessment.allowed_reading_ids,
        }
        self.connection.execute(
            """
            INSERT INTO assessments (
                text, text_length, bcc_frequency,
                candidate_class, integration_policy, decision_status,
                confidence, rationale, assessor, evidence_json,
                allowed_reading_ids_json, created_at_utc, updated_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(text) DO UPDATE SET
                text_length = excluded.text_length,
                bcc_frequency = excluded.bcc_frequency,
                candidate_class = excluded.candidate_class,
                integration_policy = excluded.integration_policy,
                decision_status = excluded.decision_status,
                confidence = excluded.confidence,
                rationale = excluded.rationale,
                assessor = excluded.assessor,
                evidence_json = excluded.evidence_json,
                allowed_reading_ids_json = excluded.allowed_reading_ids_json,
                updated_at_utc = excluded.updated_at_utc
            """,
            (
                assessment.text,
                len(assessment.text),
                int(assessment.evidence.get("bcc_frequency", 0)),
                assessment.candidate_class.value,
                assessment.integration_policy.value,
                assessment.status.value,
                assessment.confidence,
                assessment.rationale,
                assessment.assessor,
                json.dumps(assessment.evidence, ensure_ascii=False, sort_keys=True),
                json.dumps(assessment.allowed_reading_ids),
                created,
                now,
            ),
        )
        self.connection.execute(
            """
            INSERT INTO audit_events(text, event_type, assessor, payload_json, created_at_utc)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                assessment.text,
                "assessment_created" if current is None else "assessment_updated",
                assessment.assessor,
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                now,
            ),
        )
        self.connection.commit()
        return True

    def approved_component(self, text: str) -> CandidateAssessment | None:
        assessment = self.get(text)
        if assessment is None or assessment.status is not DecisionStatus.APPROVED:
            return None
        if assessment.integration_policy not in {
            IntegrationPolicy.STATIC_KEEP,
            IntegrationPolicy.DYNAMIC_COMPONENT,
        }:
            return None
        return assessment

    def count_by_status(self) -> dict[str, int]:
        return {
            str(status): int(count)
            for status, count in self.connection.execute(
                "SELECT decision_status, COUNT(*) FROM assessments GROUP BY decision_status"
            )
        }

    def add_context(self, evidence: ContextEvidence) -> bool:
        cursor = self.connection.execute(
            """
            INSERT OR IGNORE INTO context_evidence(
                text, left_context, matched_text, right_context,
                source, source_reference, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                evidence.text,
                evidence.left_context,
                evidence.matched_text,
                evidence.right_context,
                evidence.source,
                evidence.source_reference,
                _now(),
            ),
        )
        self.connection.commit()
        return cursor.rowcount > 0

    def contexts(self, text: str, *, limit: int = 20) -> tuple[ContextEvidence, ...]:
        rows = self.connection.execute(
            """
            SELECT text, left_context, matched_text, right_context,
                   source, source_reference
            FROM context_evidence
            WHERE text = ?
            ORDER BY source, source_reference, id
            LIMIT ?
            """,
            (text, limit),
        )
        return tuple(
            ContextEvidence(
                text=str(row["text"]),
                left_context=str(row["left_context"]),
                matched_text=str(row["matched_text"]),
                right_context=str(row["right_context"]),
                source=str(row["source"]),
                source_reference=str(row["source_reference"]),
            )
            for row in rows
        )
