#!/usr/bin/env python3
"""Audit both external Pinyin dictionaries with one shared policy."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from internal_data.hanzi_pinyin.hanzi_pinyin_source_io import parse_hanzi_pinyin_txt
from yime.utils.dictionary_pinyin_compliance import (
    DEFAULT_POLICY_PATH,
    load_policy,
    review_reading,
    review_syllable,
    summarize_reviews,
)


def audit_hanzi(path: Path, policy: dict) -> tuple[list[dict], list]:
    issues: list[dict] = []
    all_reviews = []
    for row in parse_hanzi_pinyin_txt(path):
        candidates = [part.strip() for part in row.readings.split(",") if part.strip()]
        if row.common_reading and row.common_reading not in candidates:
            issues.append({"source": "hanzi", "entry": row.hanzi, "codepoint": row.codepoint,
                           "severity": "error", "rule_id": "SRC-COMMON-NOT-IN-READINGS",
                           "detail": row.common_reading})
        if row.is_single != (1 if len(candidates) == 1 else 0):
            issues.append({"source": "hanzi", "entry": row.hanzi, "codepoint": row.codepoint,
                           "severity": "error", "rule_id": "SRC-IS-SINGLE-MISMATCH",
                           "detail": str(len(candidates))})
        for marked in candidates:
            review = review_syllable(marked, policy, codepoint=row.codepoint)
            all_reviews.append(review)
            if review.status in {
                "rejected",
                "canonical_alias",
                "source_correction",
            } or review.known_exclusion:
                issues.append({"source": "hanzi", "entry": row.hanzi, "codepoint": row.codepoint,
                               "severity": "error" if review.status == "rejected" else "notice",
                               **asdict(review)})
    return issues, all_reviews


def audit_phrase(path: Path, policy: dict) -> tuple[list[dict], list]:
    issues: list[dict] = []
    all_reviews = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            issues.append({"source": "phrase", "line": line_number, "severity": "error",
                           "rule_id": "SRC-MISSING-SEPARATOR", "detail": line})
            continue
        phrase, pinyin = line.split(":", 1)
        pinyin = pinyin.split("#", 1)[0].strip()
        reviews = review_reading(pinyin, policy)
        all_reviews.extend(reviews)
        if not phrase.strip() or not reviews:
            issues.append({"source": "phrase", "line": line_number, "severity": "error",
                           "rule_id": "SRC-EMPTY-PHRASE-OR-PINYIN", "detail": line})
            continue
        if len(reviews) != len(phrase.strip()):
            issues.append({"source": "phrase", "line": line_number, "entry": phrase.strip(),
                           "severity": "error", "rule_id": "SRC-SYLLABLE-COUNT-MISMATCH",
                           "detail": f"phrase={len(phrase.strip())}, pinyin={len(reviews)}"})
        for review in reviews:
            if review.status in {"rejected", "canonical_alias", "source_correction"}:
                issues.append({"source": "phrase", "line": line_number, "entry": phrase.strip(),
                               "severity": "error" if not review.accepted else "notice",
                               **asdict(review)})
    return issues, all_reviews


def write_tsv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = sorted({key for row in rows for key in row}) or ["source", "severity", "rule_id"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="在音节解码前审查两个外部字典的拼音。")
    parser.add_argument("--hanzi", type=Path, default=ROOT / "external_data" / "hanzi_pinyin.txt")
    parser.add_argument("--phrase", type=Path, default=ROOT / "external_data" / "phrase_pinyin.txt")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    parser.add_argument("--output-dir", type=Path, default=ROOT / ".generated" / "pinyin_compliance")
    args = parser.parse_args()

    policy = load_policy(args.policy)
    hanzi_issues, hanzi_reviews = audit_hanzi(args.hanzi, policy)
    phrase_issues, phrase_reviews = audit_phrase(args.phrase, policy)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_tsv(args.output_dir / "hanzi_pinyin_review.tsv", hanzi_issues)
    write_tsv(args.output_dir / "phrase_pinyin_review.tsv", phrase_issues)
    summary = {
        "schema_version": "dictionary-pinyin-compliance-report-v1",
        "policy": str(args.policy),
        "hanzi": {"syllables": len(hanzi_reviews), "statuses": summarize_reviews(hanzi_reviews),
                  "errors": sum(row.get("severity") == "error" for row in hanzi_issues),
                  "notices": sum(row.get("severity") == "notice" for row in hanzi_issues)},
        "phrase": {"syllables": len(phrase_reviews), "statuses": summarize_reviews(phrase_reviews),
                   "errors": sum(row.get("severity") == "error" for row in phrase_issues),
                   "notices": sum(row.get("severity") == "notice" for row in phrase_issues)},
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if summary["hanzi"]["errors"] or summary["phrase"]["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
