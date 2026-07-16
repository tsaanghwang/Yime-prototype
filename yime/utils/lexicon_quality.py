from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

# 助词 / 语气词尾字：命中后仅记为 warning，供人工审阅，不自动删除。
PARTICLE_SUFFIX_CHARS = frozenset("的了了吗呢吧啊嘛呀哦哈呗哇呐麽")

# 常见短语白名单：即使以助词结尾也跳过 suffix_particle 警告。
PARTICLE_SUFFIX_WHITELIST = frozenset({
    "你的",
    "我的",
    "他的",
    "她的",
    "它的",
    "我们的",
    "你们的",
    "他们的",
    "好的",
    "对了",
    "行了",
    "可以了",
    "知道了",
    "怎么了",
    "为什么",
    "是不是",
})

REQUIRED_CANDIDATE_FIELDS = (
    "text",
    "entry_type",
    "entry_id",
    "pinyin_tone",
    "yime_code",
    "sort_weight",
    "is_common",
    "text_length",
    "updated_at",
)

RUNTIME_CANDIDATES_SQL = """
SELECT
    text,
    entry_type,
    CAST(entry_id AS TEXT) AS entry_id,
    pinyin_tone,
    yime_code,
    sort_weight,
    is_common,
    text_length,
    updated_at
FROM runtime_candidates
ORDER BY yime_code, sort_weight DESC, text
"""

SOURCE_PHRASE_SQL = """
SELECT id, phrase, marked_pinyin, numeric_pinyin, reading_rank
FROM phrase_readings
ORDER BY id
"""


def make_report(*, sample_limit: int, inputs: dict[str, str]) -> dict[str, Any]:
    return {
        "tool": "lexicon_lint",
        "inputs": inputs,
        "summary": {
            "candidate_rows": 0,
            "source_phrase_rows": 0,
            "error_count": 0,
            "warning_count": 0,
            "suffix_particle_count": 0,
            "placeholder_phrase_count": 0,
        },
        "errors": defaultdict(list),
        "warnings": defaultdict(list),
        "sample_limit": sample_limit,
        "notes": [
            "suffix_particle 规则仅作审阅提示，当前不会自动清理词库。",
            "请配合 docs/LEXICON_LINT.md 使用；确认后再考虑 lexicon_clean --apply（尚未启用）。",
        ],
    }


def record_issue(
    report: dict[str, Any],
    level: str,
    category: str,
    detail: dict[str, Any],
) -> None:
    summary_key = "error_count" if level == "errors" else "warning_count"
    report["summary"][summary_key] += 1
    if category == "suffix_particle":
        report["summary"]["suffix_particle_count"] += 1
    if category == "placeholder_phrase_code":
        report["summary"]["placeholder_phrase_count"] += 1
    bucket = report[level][category]
    if len(bucket) < report["sample_limit"]:
        bucket.append(detail)


def finalize_report(report: dict[str, Any]) -> dict[str, Any]:
    report["errors"] = {key: value for key, value in sorted(report["errors"].items())}
    report["warnings"] = {key: value for key, value in sorted(report["warnings"].items())}
    return report


def ends_with_particle(text: str, *, min_length: int = 2) -> bool:
    stripped = str(text or "").strip()
    if len(stripped) < min_length:
        return False
    return stripped[-1] in PARTICLE_SUFFIX_CHARS


def is_whitelisted_phrase(text: str) -> bool:
    return str(text or "").strip() in PARTICLE_SUFFIX_WHITELIST


def is_placeholder_phrase(entry_type: str, yime_code: str, pinyin_tone: str) -> bool:
    return (
        entry_type == "phrase"
        and str(yime_code or "").strip() != ""
        and str(yime_code or "").strip() == str(pinyin_tone or "").strip()
    )


def lint_candidate_row(
    report: dict[str, Any],
    *,
    code_key: str,
    candidate: dict[str, Any],
    source: str,
) -> None:
    report["summary"]["candidate_rows"] += 1

    missing_fields = [field for field in REQUIRED_CANDIDATE_FIELDS if field not in candidate]
    if missing_fields:
        record_issue(report, "errors", "missing_required_fields", {
            "source": source,
            "code_key": code_key,
            "text": candidate.get("text"),
            "missing_fields": missing_fields,
        })
        return

    text = str(candidate.get("text") or "")
    entry_type = str(candidate.get("entry_type") or "")
    yime_code = str(candidate.get("yime_code") or "")
    pinyin_tone = str(candidate.get("pinyin_tone") or "")

    if yime_code != code_key:
        record_issue(report, "errors", "json_code_key_mismatch", {
            "source": source,
            "code_key": code_key,
            "text": text,
            "candidate_yime_code": yime_code,
        })

    if entry_type not in {"char", "phrase"}:
        record_issue(report, "errors", "invalid_entry_type", {
            "source": source,
            "text": text,
            "entry_type": entry_type,
        })

    if is_placeholder_phrase(entry_type, yime_code, pinyin_tone):
        record_issue(report, "warnings", "placeholder_phrase_code", {
            "source": source,
            "text": text,
            "pinyin_tone": pinyin_tone,
            "yime_code": yime_code,
            "entry_id": candidate.get("entry_id"),
        })

    if entry_type == "phrase" and ends_with_particle(text) and not is_whitelisted_phrase(text):
        sort_weight = float(candidate.get("sort_weight") or 0.0)
        record_issue(report, "warnings", "suffix_particle", {
            "source": source,
            "text": text,
            "suffix_char": text[-1],
            "pinyin_tone": pinyin_tone,
            "sort_weight": sort_weight,
            "entry_id": candidate.get("entry_id"),
        })


def lint_runtime_json_payload(
    payload: dict[str, Any],
    report: dict[str, Any],
    *,
    source_label: str,
) -> None:
    by_code = payload.get("by_code")
    if not isinstance(by_code, dict):
        record_issue(report, "errors", "invalid_runtime_json", {
            "source": source_label,
            "detail": "top-level by_code is missing or not an object",
        })
        return

    for code_key, candidates in by_code.items():
        if not isinstance(candidates, list):
            record_issue(report, "errors", "invalid_runtime_json", {
                "source": source_label,
                "code_key": code_key,
                "detail": "candidate bucket is not a list",
            })
            continue
        for candidate in candidates:
            if not isinstance(candidate, dict):
                record_issue(report, "errors", "invalid_runtime_json", {
                    "source": source_label,
                    "code_key": code_key,
                    "detail": "candidate row is not an object",
                })
                continue
            lint_candidate_row(
                report,
                code_key=str(code_key),
                candidate=candidate,
                source=source_label,
            )


def load_runtime_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def lint_runtime_json_file(path: Path, report: dict[str, Any]) -> None:
    payload = load_runtime_json(path)
    lint_runtime_json_payload(payload, report, source_label=str(path))


def lint_runtime_db_file(path: Path, report: dict[str, Any]) -> None:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(RUNTIME_CANDIDATES_SQL).fetchall()
    finally:
        conn.close()

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        candidate = {key: row[key] for key in row.keys()}
        grouped[str(candidate["yime_code"])].append(candidate)

    lint_runtime_json_payload(
        {"by_code": grouped},
        report,
        source_label=str(path),
    )


def lint_source_db_file(path: Path, report: dict[str, Any]) -> None:
    conn = sqlite3.connect(path)
    try:
        rows = conn.execute(SOURCE_PHRASE_SQL).fetchall()
    finally:
        conn.close()

    for row_id, phrase, marked_pinyin, numeric_pinyin, reading_rank in rows:
        report["summary"]["source_phrase_rows"] += 1
        phrase_text = str(phrase or "").strip()
        if not phrase_text:
            record_issue(report, "errors", "empty_source_phrase", {
                "source": str(path),
                "id": row_id,
            })
            continue

        if ends_with_particle(phrase_text) and not is_whitelisted_phrase(phrase_text):
            record_issue(report, "warnings", "source_suffix_particle", {
                "source": str(path),
                "id": row_id,
                "phrase": phrase_text,
                "suffix_char": phrase_text[-1],
                "marked_pinyin": marked_pinyin,
                "numeric_pinyin": numeric_pinyin,
                "reading_rank": reading_rank,
            })


def iter_clean_targets(report: dict[str, Any]) -> Iterable[dict[str, Any]]:
    """Return warning samples that a future clean step might act on."""
    for category in ("suffix_particle", "placeholder_phrase_code", "source_suffix_particle"):
        for item in report.get("warnings", {}).get(category, []):
            yield {"category": category, **item}
