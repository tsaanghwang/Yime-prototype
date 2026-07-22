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


SCHEMA_VERSION = "yime-input-candidate-model-v2"


SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS candidate_universe (
    text TEXT PRIMARY KEY,
    text_length INTEGER NOT NULL,
    bcc_frequency INTEGER NOT NULL,
    has_bcc_evidence INTEGER NOT NULL CHECK (has_bcc_evidence IN (0, 1)),
    has_gated_reading INTEGER NOT NULL CHECK (has_gated_reading IN (0, 1)),
    has_source_rejection INTEGER NOT NULL CHECK (has_source_rejection IN (0, 1)),
    baseline_class TEXT NOT NULL,
    baseline_policy TEXT NOT NULL,
    baseline_rule TEXT NOT NULL,
    last_seen_generation TEXT NOT NULL
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS candidate_universe_review_idx
    ON candidate_universe(bcc_frequency DESC, baseline_policy, baseline_class, text);
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
DROP VIEW IF EXISTS v_review_queue;
CREATE VIEW v_review_queue AS
SELECT u.text, u.text_length, u.bcc_frequency,
       COALESCE(a.candidate_class, u.baseline_class) AS candidate_class,
       COALESCE(a.integration_policy, u.baseline_policy) AS integration_policy,
       COALESCE(a.decision_status, 'proposed') AS decision_status,
       a.confidence,
       COALESCE(a.rationale, u.baseline_rule) AS rationale,
       COALESCE(a.assessor, 'baseline:' || u.baseline_rule) AS assessor,
       COALESCE(a.evidence_json, '{}') AS evidence_json,
       a.updated_at_utc
FROM candidate_universe AS u
LEFT JOIN assessments AS a USING (text)
WHERE COALESCE(a.decision_status, 'proposed') IN ('proposed', 'deferred');
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

    def sync_candidate_universe(self, *, source_database: Path, policy_path: Path) -> int:
        """Materialize the complete source candidate set with compact baseline decisions."""
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        generation = _now()
        self.connection.execute(
            "ATTACH DATABASE ? AS source_lexicon",
            (str(source_database.resolve()),),
        )

        def source_read_only(
            action_code: int,
            _argument_1: str | None,
            _argument_2: str | None,
            database_name: str | None,
            _trigger_name: str | None,
        ) -> int:
            if database_name == "source_lexicon" and action_code not in {
                sqlite3.SQLITE_READ,
                sqlite3.SQLITE_SELECT,
                sqlite3.SQLITE_FUNCTION,
            }:
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        self.connection.set_authorizer(source_read_only)
        try:
            self.connection.execute(
                """
                UPDATE candidate_universe
                SET bcc_frequency = 0,
                    has_bcc_evidence = 0,
                    has_gated_reading = 0,
                    has_source_rejection = 0,
                    baseline_class = 'unknown',
                    baseline_policy = 'needs_review',
                    baseline_rule = 'not_seen_in_current_source'
                """
            )
            self.connection.execute(
                """
                INSERT INTO candidate_universe(
                    text, text_length, bcc_frequency, has_bcc_evidence,
                    has_gated_reading, has_source_rejection,
                    baseline_class, baseline_policy, baseline_rule,
                    last_seen_generation
                )
                SELECT text, LENGTH(text), MAX(bcc_frequency),
                       CASE WHEN MAX(bcc_frequency) > 0 THEN 1 ELSE 0 END,
                       1, 0,
                       CASE WHEN LENGTH(text) = 1 THEN 'single_character'
                            ELSE 'lexical_candidate' END,
                       CASE WHEN LENGTH(text) = 1 THEN 'static_keep'
                            ELSE 'needs_review' END,
                       CASE WHEN LENGTH(text) = 1 THEN 'single_character_with_gated_reading'
                            ELSE 'gated_reading_unclassified' END,
                       ?
                FROM source_lexicon.canonical_readings
                GROUP BY text
                ON CONFLICT(text) DO UPDATE SET
                    text_length = excluded.text_length,
                    bcc_frequency = excluded.bcc_frequency,
                    has_bcc_evidence = excluded.has_bcc_evidence,
                    has_gated_reading = 1,
                    has_source_rejection = 0,
                    baseline_class = excluded.baseline_class,
                    baseline_policy = excluded.baseline_policy,
                    baseline_rule = excluded.baseline_rule,
                    last_seen_generation = excluded.last_seen_generation
                """,
                (generation,),
            )
            self.connection.execute(
                """
                INSERT INTO candidate_universe(
                    text, text_length, bcc_frequency, has_bcc_evidence,
                    has_gated_reading, has_source_rejection,
                    baseline_class, baseline_policy, baseline_rule,
                    last_seen_generation
                )
                SELECT text, LENGTH(text), frequency, 1, 0, 0,
                       'unknown', 'needs_review', 'bcc_without_gated_reading', ?
                FROM source_lexicon.bcc_frequency
                WHERE 1
                ON CONFLICT(text) DO UPDATE SET
                    text_length = excluded.text_length,
                    bcc_frequency = excluded.bcc_frequency,
                    has_bcc_evidence = 1,
                    last_seen_generation = excluded.last_seen_generation
                """,
                (generation,),
            )
            self.connection.execute(
                """
                INSERT INTO candidate_universe(
                    text, text_length, bcc_frequency, has_bcc_evidence,
                    has_gated_reading, has_source_rejection,
                    baseline_class, baseline_policy, baseline_rule,
                    last_seen_generation
                )
                SELECT text, LENGTH(text), 0, 0, 0, 1,
                       'unknown', 'needs_review', 'rejected_reading_only', ?
                FROM source_lexicon.rejections
                GROUP BY text
                ON CONFLICT(text) DO UPDATE SET
                    has_source_rejection = 1,
                    baseline_rule = CASE
                        WHEN candidate_universe.has_gated_reading = 1
                        THEN candidate_universe.baseline_rule
                        ELSE 'rejected_reading_only'
                    END,
                    last_seen_generation = excluded.last_seen_generation
                """,
                (generation,),
            )

            hints = sorted(
                policy.get("source_category_hints", {}).items(),
                key=lambda item: (int(item[1].get("priority", 1000)), item[0]),
                reverse=True,
            )
            for category_key, hint in hints:
                source, category = category_key.split(":", 1)
                self.connection.execute(
                    """
                    UPDATE candidate_universe
                    SET baseline_class = ?, baseline_policy = ?, baseline_rule = ?
                    WHERE has_gated_reading = 1
                      AND text_length > 1
                      AND text IN (
                          SELECT text
                          FROM source_lexicon.accepted_readings
                          WHERE source = ? AND source_category = ?
                      )
                    """,
                    (
                        hint["candidate_class"],
                        hint["integration_policy"],
                        f"source_category:{category_key}",
                        source,
                        category,
                    ),
                )
            self.connection.execute(
                "DELETE FROM candidate_universe WHERE last_seen_generation <> ?",
                (generation,),
            )
            self.connection.execute(
                """
                INSERT INTO metadata(key, value) VALUES ('candidate_universe_generation', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (generation,),
            )
            count = int(
                self.connection.execute("SELECT COUNT(*) FROM candidate_universe").fetchone()[0]
            )
            self.connection.commit()
            return count
        except Exception:
            self.connection.rollback()
            raise
        finally:
            self.connection.set_authorizer(None)
            self.connection.execute("DETACH DATABASE source_lexicon")

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

    def effective(self, text: str) -> CandidateAssessment | None:
        universe_row = self.connection.execute(
            "SELECT * FROM candidate_universe WHERE text = ?",
            (text,),
        ).fetchone()
        if universe_row is None:
            return None
        assessment = self.get(text)
        if assessment is not None:
            return assessment
        return CandidateAssessment(
            text=str(universe_row["text"]),
            candidate_class=CandidateClass(universe_row["baseline_class"]),
            integration_policy=IntegrationPolicy(universe_row["baseline_policy"]),
            status=DecisionStatus.PROPOSED,
            rationale=str(universe_row["baseline_rule"]),
            assessor=f"baseline:{universe_row['baseline_rule']}",
            evidence={
                "bcc_frequency": int(universe_row["bcc_frequency"]),
                "has_bcc_evidence": bool(universe_row["has_bcc_evidence"]),
                "has_gated_reading": bool(universe_row["has_gated_reading"]),
                "has_source_rejection": bool(universe_row["has_source_rejection"]),
            },
        )

    def put(self, assessment: CandidateAssessment, *, overwrite: bool = True) -> bool:
        if self.connection.execute(
            "SELECT 1 FROM candidate_universe WHERE text = ?",
            (assessment.text,),
        ).fetchone() is None:
            raise ValueError(f"assessment text is outside the candidate universe: {assessment.text}")
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

    def universe_count(self) -> int:
        return int(self.connection.execute("SELECT COUNT(*) FROM candidate_universe").fetchone()[0])

    def review_queue_count(self) -> int:
        return int(self.connection.execute("SELECT COUNT(*) FROM v_review_queue").fetchone()[0])

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
