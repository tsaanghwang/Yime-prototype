#!/usr/bin/env python3
"""Generate the manual follow-up checklist for component-learning replay.

The real librime replay can select a target only when the complete target is
visible in the candidate menu.  Sentence compositions that require moving the
caret and correcting an inner segment therefore need a short manual follow-up.
This tool also lists cold-correct controls whose top candidate changed after
the deliberately aggressive same-code learning pass.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


CHECKLIST_FIELDS = (
    "category",
    "target",
    "input_code",
    "cold_top",
    "after_learning_top",
    "cold_start_observation",
    "correction_count",
    "second_input_ok",
    "restart_ok",
    "interference_ok",
    "notes",
)


def load_report(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        report = json.load(stream)
    cases = report.get("cases", report.get("results"))
    if not isinstance(cases, list):
        raise ValueError(f"{path} does not contain a cases list")
    report["cases"] = cases
    return report


def checklist_rows(
    report: dict[str, Any],
    observations: dict[str, dict[str, object]] | None = None,
) -> list[dict[str, str]]:
    observations = observations or {}
    rows: list[dict[str, str]] = []
    for result in report["cases"]:
        if (
            result.get("constructible")
            and result.get("production_target_top1")
            and not result.get("after_one_target_top1")
        ):
            rows.append(
                _row(
                    category="segment_correction",
                    result=result,
                    after_top=result.get("after_one_top", ""),
                    observation=observations.get(str(result.get("target", ""))),
                )
            )

        if (
            result.get("interference_control")
            and not result.get("interference_top1_preserved")
        ):
            rows.append(
                _row(
                    category="same_code_interference",
                    result=result,
                    after_top=result.get("after_learning_control_top", ""),
                    observation=observations.get(str(result.get("target", ""))),
                )
            )
    return rows


def _row(
    *,
    category: str,
    result: dict[str, Any],
    after_top: object,
    observation: dict[str, object] | None,
) -> dict[str, str]:
    row = {
        "category": category,
        "target": str(result.get("target", "")),
        "input_code": str(result.get("input", result.get("code", ""))),
        "cold_top": str(result.get("cold_top", "")),
        "after_learning_top": str(after_top),
        "cold_start_observation": "",
        "correction_count": "",
        "second_input_ok": "",
        "restart_ok": "",
        "interference_ok": "",
        "notes": "",
    }
    if observation:
        for field in CHECKLIST_FIELDS:
            if field in observation:
                row[field] = str(observation[field])
    return row


def write_tsv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CHECKLIST_FIELDS, dialect="excel-tab")
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(
    path: Path, report_path: Path, report: dict[str, Any], rows: list[dict[str, str]]
) -> None:
    segment_rows = [row for row in rows if row["category"] == "segment_correction"]
    interference_rows = [
        row for row in rows if row["category"] == "same_code_interference"
    ]
    summary = report.get("summary", {})
    evaluation_groups_value = report.get("evaluation_groups", {})
    if isinstance(evaluation_groups_value, dict):
        evaluation_groups = evaluation_groups_value
    else:
        evaluation_groups = {
            group.get("name"): group
            for group in evaluation_groups_value
            if isinstance(group, dict)
        }
    qualified = evaluation_groups.get("constructible_and_production_top1", {})
    manually_confirmed = sum(
        row["second_input_ok"].strip().lower() in {"是", "yes", "true", "1"}
        for row in segment_rows
    )
    qualified_cases = int(qualified.get("cases", 0) or 0)
    automatic_passes = int(qualified.get("after_one_target_top1", 0) or 0)
    combined_passes = automatic_passes + manually_confirmed

    lines = [
        "# 基础部件学习人工复测清单",
        "",
        f"- 来源报告：`{report_path}`",
        f"- 自动样本：{summary.get('cases', '')}",
        (
            "- 99% 目标口径："
            f"{automatic_passes}/"
            f"{qualified_cases} = "
            f"{_percent(qualified.get('after_one_top1_rate'))}"
        ),
        (
            "- 补充人工验证后："
            f"{combined_passes}/{qualified_cases} = "
            f"{_percent(combined_passes / qualified_cases if qualified_cases else 0)}"
            f"（自动遗留项中已确认 {manually_confirmed} 条）"
        ),
        (
            "- 学习后重启保持："
            f"{summary.get('after_restart_target_top1', '')}/"
            f"{summary.get('restart_eligible', '')} = "
            f"{_percent(summary.get('restart_persistence_rate'))}"
        ),
        (
            "- 同码干扰保持："
            f"{summary.get('interference_top1_preserved', '')}/"
            f"{summary.get('interference_controls', '')} = "
            f"{_percent(summary.get('interference_preservation_rate'))}"
        ),
        "",
        "## 操作方法",
        "",
        "1. 选择“基础部件测试”，清空或换用新的用户词库，输入目标句。",
        "2. 若整句不是首选，通过光标移动和候选点选完成分段纠正，记录点选次数。",
        "3. 再输入一次，记录能否直接回车上屏；退出并重新启动输入法后再测一次。",
        "4. 同码干扰项先确认目标原为首选，再执行学习批次，检查目标是否仍为首选。",
        "",
        f"## 需要分段纠正的句子（{len(segment_rows)}）",
        "",
        "|目标|自动冷启动首选|第二次直接上屏|重启后直接上屏|备注|",
        "|---|---|---|---|---|",
    ]
    lines.extend(
        (
            f"|{_md(row['target'])}|{_md(row['cold_top'])}|"
            f"{_md(row['second_input_ok'])}|{_md(row['restart_ok'])}|"
            f"{_md(row['notes'])}|"
        )
        for row in segment_rows
    )
    lines.extend(
        [
            "",
            f"## 需要复核的同码干扰（{len(interference_rows)}）",
            "",
            "|目标|学习前首选|学习后首选|目标仍为首选|备注|",
            "|---|---|---|---|---|",
        ]
    )
    lines.extend(
        (
            f"|{_md(row['target'])}|{_md(row['cold_top'])}|"
            f"{_md(row['after_learning_top'])}|"
            f"{_md(row['interference_ok'])}|{_md(row['notes'])}|"
        )
        for row in interference_rows
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _percent(value: object) -> str:
    if isinstance(value, (int, float)):
        return f"{value * 100:.4f}%"
    return ""


def _md(value: str) -> str:
    return value.replace("|", r"\|").replace("\n", " ")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--observations",
        type=Path,
        help="Optional JSON object keyed by target text with manually observed fields",
    )
    args = parser.parse_args()

    report_path = args.report.resolve()
    report = load_report(report_path)
    observations: dict[str, dict[str, object]] = {}
    if args.observations:
        loaded = json.loads(args.observations.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("--observations must contain a JSON object")
        observations = loaded
    rows = checklist_rows(report, observations)
    tsv_path = args.output_dir / "component_learning_manual_checklist.tsv"
    markdown_path = args.output_dir / "component_learning_manual_checklist.md"
    write_tsv(tsv_path, rows)
    write_markdown(markdown_path, report_path, report, rows)
    print(
        json.dumps(
            {
                "rows": len(rows),
                "segment_correction": sum(
                    row["category"] == "segment_correction" for row in rows
                ),
                "same_code_interference": sum(
                    row["category"] == "same_code_interference" for row in rows
                ),
                "tsv": str(tsv_path.resolve()),
                "markdown": str(markdown_path.resolve()),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
