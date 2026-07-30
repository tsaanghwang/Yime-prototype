#!/usr/bin/env python3
"""Plan de/suo construction components and evaluate a prebuilt component."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from yime.input_model.construction_components import (
    ConstructionFamily,
    evaluate_prebuilt_component,
    plan_construction_components,
)


DEFAULT_SOURCE = (
    ROOT / ".generated" / "lexicon_source_bundle" / "source_lexicon.sqlite3"
)
DEFAULT_CAPACITY = (
    ROOT / ".generated" / "static_lexicon_capacity" / "static_capacity.sqlite3"
)
DEFAULT_POLICY = ROOT / "internal_data" / "construction_component_policy.json"
DEFAULT_DECISIONS = ROOT / "internal_data" / "lexicon_review_decisions.json"
DEFAULT_INPUT_MODEL = (
    ROOT / ".generated" / "input_candidate_model" / "input_model.sqlite3"
)
DEFAULT_OUTPUT = ROOT / ".generated" / "construction_component_evaluation"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-database", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--capacity-database", type=Path, default=DEFAULT_CAPACITY)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--decision-catalog", type=Path, default=DEFAULT_DECISIONS)
    parser.add_argument("--input-model-database", type=Path, default=DEFAULT_INPUT_MODEL)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--component-text", default="般的")
    parser.add_argument("--component-pinyin", default="ban1 de5")
    return parser.parse_args()


def _markdown(payload: dict[str, object]) -> str:
    evaluation = payload["prebuilt_evaluation"]
    component = evaluation["component"]
    metrics = evaluation["metrics"]
    family_counts = payload["family_counts"]
    role_counts = payload["role_counts"]
    return "\n".join(
        [
            "# “的字结构 / 所字结构”预制部件评估",
            "",
            "本报告只消费来源读音和静态容量证据，不修改来源词库或运行词典。",
            "",
            "## 构式候选",
            "",
            f"- 的字结构候选：`{family_counts.get('de_construction', 0)}`",
            f"- 所字结构候选：`{family_counts.get('suo_construction', 0)}`",
            f"- display_and_component：`{role_counts.get('display_and_component', 0)}`",
            f"- component_only_candidate：`{role_counts.get('component_only_candidate', 0)}`",
            f"- runtime_generated：`{role_counts.get('runtime_generated', 0)}`",
            "",
            f"## 预制“{component['text']}”A/B",
            "",
            f"- 目标读音：`{evaluation['target_readings']}`",
            f"- 最短分解减少部件数的目标：`{metrics['minimum_part_count_improved']}`",
            f"- 总共减少部件数：`{metrics['total_parts_saved']}`",
            f"- 最短路径使用该部件：`{metrics['minimum_paths_using_component']}`",
            f"- 组合步数改善率：`{metrics['minimum_part_count_improvement_ratio']:.2%}`",
            f"- 同文同音结构竞争：`{metrics['new_minimum_segmentation_ambiguities']}`"
            f"（`{metrics['structural_competition_ratio']:.2%}`）",
            f"- 用户可见输出歧义：`{metrics['user_visible_output_ambiguities']}`",
            f"- 决策：`{evaluation['decision']}`",
            "",
            "说明：递归运行时按最终文本去重，同文同音的不同切分只属于内部结构竞争，"
            "不直接算作用户可见歧义。预制门槛综合考察组合步数改善率与结构竞争率。",
            "",
        ]
    )


def main() -> int:
    args = parse_args()
    candidates = plan_construction_components(
        capacity_database=args.capacity_database,
        policy_path=args.policy,
        decision_catalog=args.decision_catalog,
        input_model_database=args.input_model_database,
    )
    evaluation = evaluate_prebuilt_component(
        source_database=args.source_database,
        policy_path=args.policy,
        component_text=args.component_text,
        component_numeric_pinyin=args.component_pinyin,
    )
    payload = {
        "schema_version": 1,
        "tool": "evaluate_construction_components",
        "inputs": {
            "source_database": str(args.source_database.resolve()),
            "capacity_database": str(args.capacity_database.resolve()),
            "policy": str(args.policy.resolve()),
            "decision_catalog": str(args.decision_catalog.resolve()),
            "input_model_database": str(args.input_model_database.resolve()),
        },
        "family_counts": dict(Counter(item.family.value for item in candidates)),
        "role_counts": dict(Counter(item.proposed_role for item in candidates)),
        "top_candidates": {
            family.value: [
                {
                    **item.__dict__,
                    "family": item.family.value,
                }
                for item in candidates
                if item.family is family
            ][:100]
            for family in ConstructionFamily
        },
        "prebuilt_evaluation": evaluation,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "report.json"
    markdown_path = args.output_dir / "report.md"
    plan_path = args.output_dir / "candidate_plan.tsv"
    with plan_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=(
                "family",
                "text",
                "numeric_pinyin",
                "proposed_role",
                "decision_status",
                "bcc_frequency",
                "dependent_reading_count",
                "dependent_frequency",
                "utility_score",
                "current_disposition",
                "decision_rationale",
            ),
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for item in candidates:
            writer.writerow(
                {
                    **item.__dict__,
                    "family": item.family.value,
                }
            )
    payload["outputs"] = {
        "candidate_plan": str(plan_path.resolve()),
        "markdown": str(markdown_path.resolve()),
    }
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(_markdown(payload), encoding="utf-8")
    print(f"json: {json_path.resolve()}")
    print(f"markdown: {markdown_path.resolve()}")
    print(f"candidate_plan: {plan_path.resolve()}")
    print(f"family_counts: {payload['family_counts']}")
    print(f"role_counts: {payload['role_counts']}")
    print(f"decision: {evaluation['decision']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
