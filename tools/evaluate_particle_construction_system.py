#!/usr/bin/env python3
"""Scan typed particle constructions at every attested text position."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from yime.input_model.particle_constructions import (  # noqa: E402
    DEFAULT_POLICY_PATH,
    classify_particle_constructions,
    review_particle_construction,
)


DEFAULT_CAPACITY = (
    ROOT / ".generated" / "static_lexicon_capacity" / "static_capacity.sqlite3"
)
DEFAULT_OUTPUT = ROOT / ".generated" / "particle_construction_evaluation"


def _readonly_uri(path: Path) -> str:
    return f"file:{quote(path.resolve().as_posix(), safe='/:')}?mode=ro"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "只读扫描静态容量模型中的全部助词位置，输出构式系统、类型接口和核心角色证据。"
        )
    )
    parser.add_argument("--capacity-database", type=Path, default=DEFAULT_CAPACITY)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--maximum-text-length", type=int, default=12)
    parser.add_argument("--sample-limit", type=int, default=20)
    return parser.parse_args()


def _retain_sample(
    samples: dict[str, list[dict[str, object]]],
    construction_id: str,
    item: dict[str, object],
    limit: int,
) -> None:
    bucket = samples[construction_id]
    bucket.append(item)
    bucket.sort(
        key=lambda value: (
            -int(value["bcc_frequency"]),
            -int(value["dependent_reading_count"]),
            str(value["text"]),
        )
    )
    del bucket[limit:]


def _markdown(report: dict[str, object]) -> str:
    counts = report["counts"]
    lines = [
        "# 助词构式全位置扫描",
        "",
        "本报告只读静态容量模型；命中表示存在有类型的构式分析，不是静态准入或无效材料裁决。",
        "",
        f"- 扫描读音：`{counts['scanned_readings']}`",
        f"- 命中读音：`{counts['matched_readings']}`",
        f"- 命中字串：`{counts['matched_texts']}`",
        f"- 含内部助词的命中读音：`{counts['internal_marker_readings']}`",
        "",
        "## 构式系统",
        "",
        "| 系统 | 命中读音 |",
        "| --- | ---: |",
    ]
    for key, value in sorted(
        counts["systems"].items(),
        key=lambda item: (-item[1], item[0]),
    ):
        lines.append(f"| {key} | {value} |")
    lines.extend(
        [
            "",
            "## 建议角色",
            "",
            "| 角色 | 命中读音 |",
            "| --- | ---: |",
        ]
    )
    for key, value in sorted(
        counts["suggested_roles"].items(),
        key=lambda item: (-item[1], item[0]),
    ):
        lines.append(f"| {key} | {value} |")
    lines.extend(
        [
            "",
            "完整构式计数和高 BCC 样例见 `report.json`。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    if args.maximum_text_length < 2:
        raise SystemExit("maximum text length must be at least 2")
    if args.sample_limit < 1:
        raise SystemExit("sample limit must be positive")

    connection = sqlite3.connect(
        _readonly_uri(args.capacity_database),
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    systems: Counter[str] = Counter()
    constructions: Counter[str] = Counter()
    interfaces: Counter[str] = Counter()
    roles: Counter[str] = Counter()
    matched_texts: set[str] = set()
    samples: dict[str, list[dict[str, object]]] = defaultdict(list)
    scanned = 0
    matched = 0
    internal_marker_readings = 0
    try:
        rows = connection.execute(
            """
            SELECT i.text, r.numeric_pinyin, i.bcc_frequency,
                   i.dependent_reading_count, i.dependent_frequency,
                   i.utility_score
            FROM static_capacity_items AS i
            JOIN reading_analysis AS r USING (text)
            WHERE r.is_primary = 1
              AND i.text_length BETWEEN 2 AND ?
              AND (
                    INSTR(i.text, '的') > 0
                 OR INSTR(i.text, '地') > 0
                 OR INSTR(i.text, '得') > 0
                 OR INSTR(i.text, '着') > 0
                 OR INSTR(i.text, '了') > 0
                 OR INSTR(i.text, '过') > 0
                 OR INSTR(i.text, '吗') > 0
                 OR INSTR(i.text, '呢') > 0
                 OR INSTR(i.text, '吧') > 0
                 OR INSTR(i.text, '啊') > 0
                 OR INSTR(i.text, '嘛') > 0
                 OR INSTR(i.text, '呀') > 0
                 OR INSTR(i.text, '呗') > 0
                 OR INSTR(i.text, '哦') > 0
                 OR INSTR(i.text, '哇') > 0
                 OR INSTR(i.text, '呐') > 0
                 OR INSTR(i.text, '麽') > 0
              )
            """,
            (args.maximum_text_length,),
        )
        for row in rows:
            scanned += 1
            text = str(row["text"])
            numeric_pinyin = str(row["numeric_pinyin"])
            evidence = classify_particle_constructions(
                text,
                numeric_pinyin,
                policy_path=args.policy,
            )
            if not evidence:
                continue
            matched += 1
            matched_texts.add(text)
            internal_marker_readings += int(
                any(item.marker_index < len(text) - 1 for item in evidence)
            )
            review = review_particle_construction(
                text,
                numeric_pinyin,
                policy_path=args.policy,
            )
            roles[review.suggested_role] += 1
            for system in {item.system.value for item in evidence}:
                systems[system] += 1
            for interface in {item.interface for item in evidence}:
                interfaces[interface] += 1
            sample = {
                "text": text,
                "numeric_pinyin": numeric_pinyin,
                "bcc_frequency": int(row["bcc_frequency"]),
                "dependent_reading_count": int(row["dependent_reading_count"]),
                "dependent_frequency": int(row["dependent_frequency"]),
                "utility_score": float(row["utility_score"]),
                "suggested_role": review.suggested_role,
            }
            for construction_id in {
                item.construction_id for item in evidence
            }:
                constructions[construction_id] += 1
                _retain_sample(
                    samples,
                    construction_id,
                    sample,
                    args.sample_limit,
                )
    finally:
        connection.close()

    report = {
        "schema_version": 1,
        "tool": "evaluate_particle_construction_system",
        "inputs": {
            "capacity_database": str(args.capacity_database.resolve()),
            "policy": str(args.policy.resolve()),
            "maximum_text_length": args.maximum_text_length,
        },
        "counts": {
            "scanned_readings": scanned,
            "matched_readings": matched,
            "matched_texts": len(matched_texts),
            "internal_marker_readings": internal_marker_readings,
            "systems": dict(systems),
            "constructions": dict(constructions),
            "interfaces": dict(interfaces),
            "suggested_roles": dict(roles),
        },
        "top_samples_by_construction": dict(samples),
        "safeguards": {
            "read_only_inputs": True,
            "writes_assessments": False,
            "construction_evidence_is_not_static_admission": True,
            "construction_evidence_is_not_noise_decision": True,
        },
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "report.json"
    markdown_path = args.output_dir / "report.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    print(f"json: {json_path.resolve()}")
    print(f"markdown: {markdown_path.resolve()}")
    print(f"counts: {report['counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
