from __future__ import annotations

import sqlite3
from typing import Dict, List, Mapping

from .runtime_ranking import annotate_phrase_prefix_candidate, phrase_candidate_payload_sort_key
from .sqlite_runtime_source import SQLiteRuntimeSource


_PHRASE_PREFIX_CANDIDATE_LIMIT = 64
_RUNTIME_SQL_PRIORITY_ORDER = """
CASE
    WHEN entry_type = 'phrase' AND text_length BETWEEN 2 AND 4 THEN 0
    WHEN entry_type = 'char' THEN 1
END,
sort_weight DESC,
text,
pinyin_tone
"""


class SQLitePhraseCandidateStore:
    """SQLite-backed phrase/runtime candidate source with local caches."""

    def __init__(
        self,
        runtime_source: SQLiteRuntimeSource,
        runtime_table_name: str,
    ) -> None:
        self.runtime_source = runtime_source
        self.runtime_table_name = runtime_table_name
        self._runtime_candidate_cache: Dict[str, List[Dict[str, object]]] = {}
        self._phrase_prefix_cache: Dict[str, List[Dict[str, object]]] = {}

    def clear_caches(self) -> None:
        self._runtime_candidate_cache.clear()
        self._phrase_prefix_cache.clear()

    def load_runtime_candidates_for_code(
        self,
        lookup_code: str,
        phrase_candidate_overlays: Mapping[str, List[Dict[str, object]]],
    ) -> List[Dict[str, object]]:
        normalized_code = str(lookup_code or "").strip()
        if not normalized_code:
            return []
        cached = self._runtime_candidate_cache.get(normalized_code)
        if cached is None:
            with self.runtime_source.connect() as conn:
                rows = conn.execute(
                    f"""
                    SELECT entry_type, entry_id, text, pinyin_tone, sort_weight, is_common, text_length, updated_at
                    FROM {self.runtime_table_name}
                    WHERE yime_code = ?
                    ORDER BY {_RUNTIME_SQL_PRIORITY_ORDER}
                    """,
                    (normalized_code,),
                ).fetchall()

            cached = [dict(row) for row in rows]
            self._runtime_candidate_cache[normalized_code] = list(cached)

        merged = list(cached)
        merged.extend(phrase_candidate_overlays.get(normalized_code, []))
        return merged

    def load_phrase_prefix_candidates(
        self,
        lookup_code: str,
        phrase_candidate_overlays: Mapping[str, List[Dict[str, object]]],
    ) -> List[Dict[str, object]]:
        normalized_code = str(lookup_code or "").strip()
        if not normalized_code:
            return []
        cached = self._phrase_prefix_cache.get(normalized_code)
        if cached is not None:
            return list(cached)

        with self.runtime_source.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT entry_type, entry_id, text, pinyin_tone, yime_code, sort_weight, is_common, text_length, updated_at
                FROM {self.runtime_table_name}
                WHERE entry_type = 'phrase'
                  AND yime_code >= ?
                  AND yime_code < ?
                  AND LENGTH(yime_code) > ?
                ORDER BY sort_weight DESC, text, pinyin_tone
                LIMIT ?
                """,
                (
                    normalized_code,
                    normalized_code + "\U0010ffff",
                    len(normalized_code),
                    _PHRASE_PREFIX_CANDIDATE_LIMIT,
                ),
            ).fetchall()

        merged = [
            annotate_phrase_prefix_candidate(dict(row), len(normalized_code))
            for row in rows
        ]
        for overlay_code, overlay_candidates in phrase_candidate_overlays.items():
            normalized_overlay_code = str(overlay_code or "").strip()
            if normalized_overlay_code.startswith(normalized_code) and normalized_overlay_code != normalized_code:
                merged.extend(
                    annotate_phrase_prefix_candidate(candidate, len(normalized_code))
                    for candidate in overlay_candidates
                )

        merged.sort(key=phrase_candidate_payload_sort_key)
        cached = merged[:_PHRASE_PREFIX_CANDIDATE_LIMIT]
        self._phrase_prefix_cache[normalized_code] = list(cached)
        return list(cached)
