"""Replay fixed targets through the recursive precomposition provider."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from yime.canonical_yime_mapping import load_code_mode_map
from yime.input_method.core.layered_candidate_pipeline import (
    DynamicCandidateRequest,
    LayeredCandidatePipeline,
)
from yime.input_method.core.recursive_precomposition import (
    RecursivePrecompositionProvider,
)
from yime.utils.rime_export import (
    convert_runtime_code_to_layout_keys,
    load_runtime_symbol_to_layout_key,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dictionary_rows(
    path: Path,
) -> Iterable[tuple[str, int, str, int, int]]:
    in_data = False
    with path.open("r", encoding="utf-8-sig") as stream:
        for raw_line in stream:
            line = raw_line.rstrip("\r\n")
            if not in_data:
                if line.strip() == "...":
                    in_data = True
                continue
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            fields = line.split("\t")
            if len(fields) < 2:
                continue
            text = fields[0].strip()
            code = fields[1].replace(" ", "").strip()
            if not text or not code:
                continue
            try:
                weight = int(fields[2].strip()) if len(fields) >= 3 else 0
            except ValueError:
                weight = 0
            width = len(text)
            yield code, width, text, weight, int(width > 4)


def _prepare_index(dictionary: Path, database: Path) -> None:
    source_hash = _sha256(dictionary)
    if database.exists():
        connection = sqlite3.connect(database)
        try:
            try:
                current_hash = connection.execute(
                    "SELECT value FROM metadata WHERE key = 'source_sha256'"
                ).fetchone()
            except sqlite3.Error:
                current_hash = None
        finally:
            connection.close()
        if current_hash and str(current_hash[0]) == source_hash:
            return

    database.parent.mkdir(parents=True, exist_ok=True)
    stage = database.with_suffix(database.suffix + ".stage")
    if stage.exists():
        stage.unlink()
    connection = sqlite3.connect(stage)
    try:
        connection.executescript(
            """
            PRAGMA journal_mode = OFF;
            PRAGMA synchronous = OFF;
            CREATE TABLE metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            ) WITHOUT ROWID;
            CREATE TABLE components (
                code TEXT NOT NULL,
                syllable_count INTEGER NOT NULL,
                text TEXT NOT NULL,
                weight INTEGER NOT NULL,
                is_atom INTEGER NOT NULL,
                PRIMARY KEY (code, syllable_count, text)
            ) WITHOUT ROWID;
            """
        )
        batch: list[tuple[str, int, str, int, int]] = []
        for row in _dictionary_rows(dictionary):
            batch.append(row)
            if len(batch) >= 20_000:
                connection.executemany(
                    """
                    INSERT INTO components
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(code, syllable_count, text)
                    DO UPDATE SET
                        weight = MAX(weight, excluded.weight),
                        is_atom = MAX(is_atom, excluded.is_atom)
                    """,
                    batch,
                )
                batch.clear()
        if batch:
            connection.executemany(
                """
                INSERT INTO components
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(code, syllable_count, text)
                DO UPDATE SET
                    weight = MAX(weight, excluded.weight),
                    is_atom = MAX(is_atom, excluded.is_atom)
                """,
                batch,
            )
        connection.execute(
            "INSERT INTO metadata VALUES ('source_sha256', ?)",
            (source_hash,),
        )
        connection.commit()
    finally:
        connection.close()
    stage.replace(database)


def _metrics(cases: list[dict[str, object]]) -> dict[str, object]:
    count = len(cases)
    target_top1 = sum(bool(item["target_top1"]) for item in cases)
    target_visible = sum(bool(item["target_visible"]) for item in cases)
    production_target_top1 = sum(
        bool(item["production_target_top1"]) for item in cases
    )
    retained_production_top1 = sum(
        bool(item["production_target_top1"])
        and bool(item["target_top1"])
        for item in cases
    )
    selection_one = target_visible - target_top1
    return {
        "cases": count,
        "production_target_top1": production_target_top1,
        "retained_production_target_top1": retained_production_top1,
        "production_top1_retention_rate": (
            retained_production_top1 / production_target_top1
            if production_target_top1
            else 0.0
        ),
        "cold_target_top1": target_top1,
        "cold_target_top1_rate": target_top1 / count if count else 0.0,
        "target_visible": target_visible,
        "target_visible_rate": target_visible / count if count else 0.0,
        "selection_one_made": selection_one,
        "selection_one_promoted": selection_one,
        "after_one_target_top1": target_visible,
        "after_one_target_top1_rate": (
            target_visible / count if count else 0.0
        ),
        "selection_two_made": 0,
        "after_two_target_top1": target_visible,
        "after_two_target_top1_rate": (
            target_visible / count if count else 0.0
        ),
    }


def evaluate(
    dictionary: Path,
    index_database: Path,
    corpus: Path,
    output: Path,
    *,
    component_slot_limit: int,
    chart_beam_width: int,
    result_limit: int,
    global_candidate_limit: int,
    global_per_leading_char_limit: int,
) -> dict[str, object]:
    _prepare_index(dictionary, index_database)
    source_payload = json.loads(corpus.read_text(encoding="utf-8"))
    source_cases = list(source_payload["cases"])
    symbol_to_key = load_runtime_symbol_to_layout_key()
    code_map = {
        pinyin: convert_runtime_code_to_layout_keys(
            record.variable_code,
            symbol_to_key,
        )
        for pinyin, record in load_code_mode_map().items()
        if record.variable_code
    }
    connection = sqlite3.connect(index_database)
    connection.row_factory = sqlite3.Row

    @lru_cache(maxsize=200_000)
    def load_components(
        code: str,
        syllable_count: int,
    ) -> tuple[dict[str, object], ...]:
        rows = connection.execute(
            """
            SELECT text, weight, is_atom
            FROM components
            WHERE code = ? AND syllable_count = ?
            ORDER BY is_atom DESC, weight DESC, text
            LIMIT 32
            """,
            (code, syllable_count),
        ).fetchall()
        return tuple(
            {
                "text": str(row["text"]),
                "entry_type": (
                    "precomposition_atom"
                    if int(row["is_atom"])
                    else (
                        "char" if syllable_count == 1 else "phrase"
                    )
                ),
                "sort_weight": int(row["weight"]),
                "is_common": int(row["weight"]) > 0,
                "text_length": syllable_count,
                "_precomposition_atom": bool(row["is_atom"]),
            }
            for row in rows
        )

    provider = RecursivePrecompositionProvider(
        get_pinyin_to_code=lambda: code_map,
        get_component_candidates=load_components,
        component_slot_limit=component_slot_limit,
        chart_beam_width=chart_beam_width,
        result_limit=result_limit,
    )
    pipeline = LayeredCandidatePipeline(
        dynamic_providers=[provider],
        dynamic_candidate_limit=global_candidate_limit,
        dynamic_per_leading_char_limit=(
            global_per_leading_char_limit
        ),
    )

    results: list[dict[str, object]] = []
    for source_case in source_cases:
        input_code = str(source_case["input"])
        target = str(source_case["target"])
        syllable_count = len(target)
        candidates = pipeline.collect_dynamic_candidates(
            DynamicCandidateRequest(
                canonical_input=input_code,
                lookup_code=input_code,
                stage="D",
                syllable_count=syllable_count,
            )
        )
        texts = [
            str(candidate.get("text", "") or "")
            for candidate in candidates
        ]
        results.append(
            {
                "target": target,
                "input": input_code,
                "length_bucket": str(source_case["length_bucket"]),
                "sample_group": str(source_case["sample_group"]),
                "weight": int(source_case["weight"]),
                "production_top": str(source_case["production_top"]),
                "production_target_top1": bool(
                    source_case["production_target_top1"]
                ),
                "cold_top": texts[0] if texts else "",
                "target_top1": bool(texts and texts[0] == target),
                "target_visible": target in texts,
                "target_rank": (
                    texts.index(target) if target in texts else -1
                ),
                "candidate_count": len(texts),
            }
        )

    connection.close()
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    length_groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for result in results:
        grouped[str(result["sample_group"])].append(result)
        length_groups[str(result["length_bucket"])].append(result)
    report = {
        "schema_version": "yime-recursive-precomposition-replay-v1",
        "dictionary": str(dictionary.resolve()),
        "dictionary_sha256": _sha256(dictionary),
        "index_database": str(index_database.resolve()),
        "corpus": str(corpus.resolve()),
        "policy": {
            "base_component_lengths": [1, 2, 3, 4],
            "long_entries_are_precomposition_atoms": True,
            "recursive_chart_beam_width": provider.chart_beam_width,
            "component_slot_limit": provider.component_slot_limit,
            "result_limit": provider.result_limit,
            "global_dynamic_candidate_limit": global_candidate_limit,
            "global_per_leading_char_limit": (
                global_per_leading_char_limit
            ),
            "selection_one_effect": (
                "existing user-priority rule promotes every visible selected "
                "target; verified separately by runtime learning tests"
            ),
        },
        "summary": _metrics(results),
        "sample_groups": {
            key: _metrics(values)
            for key, values in sorted(grouped.items())
        },
        "length_groups": {
            key: _metrics(values)
            for key, values in sorted(length_groups.items())
        },
        "cases": results,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dictionary", type=Path, required=True)
    parser.add_argument("--index-database", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--component-slot-limit", type=int, default=12)
    parser.add_argument("--chart-beam-width", type=int, default=256)
    parser.add_argument("--result-limit", type=int, default=96)
    parser.add_argument("--global-candidate-limit", type=int, default=64)
    parser.add_argument(
        "--global-per-leading-char-limit",
        type=int,
        default=8,
    )
    args = parser.parse_args()
    report = evaluate(
        args.dictionary,
        args.index_database,
        args.corpus,
        args.output,
        component_slot_limit=args.component_slot_limit,
        chart_beam_width=args.chart_beam_width,
        result_limit=args.result_limit,
        global_candidate_limit=args.global_candidate_limit,
        global_per_leading_char_limit=(
            args.global_per_leading_char_limit
        ),
    )
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
