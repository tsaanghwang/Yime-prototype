#!/usr/bin/env python3
"""Apply and audit research-only erhua surface-class rules."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from syllable.analysis.erhua_surface_classes import (  # noqa: E402
    apply_surface_class_rules,
    audit_surface_classes,
)


DEFAULT_DRAFT = ROOT / "external_data" / "tmp" / "final_styles_erhua_draft.json"
DEFAULT_RULES = ROOT / "external_data" / "tmp" / "erhua_surface_class_rules.json"
DEFAULT_REPORT = ROOT / "external_data" / "tmp" / "final_styles_erhua_draft_audit.md"


def render_report(result: dict, audit: dict) -> str:
    lines = [
        "# 儿化标注草稿规则审计",
        "",
        "- 范围：研究草稿、表层类规则和校对显示；未修改正式音元源、布局或运行时。",
        f"- 规则类：{result['class_count']}。",
        f"- 表层音质变更：{result['surface_changed_members'] or '无'}。",
        f"- 仅分类元数据变更：{result['metadata_changed_members'] or '无'}。",
        f"- 已清除过期分类：{result['stale_classifications_cleared'] or '无'}。",
        f"- 未变化成员：{result['unchanged_members']}。",
        f"- 合流类不一致：{audit['mismatches'] or '无'}。",
        "",
        "## 表层类",
        "",
        "PSC 儿化结果拼写用于来源对齐；基础音质或卷舌范围不同的成员拆分为不同三段模板。技术拼音别名不进入音系草稿。",
        "`᷊`（U+1DCA）仅为 Yime 下方卷舌显示附标，标准 IPA 仍由同一结构渲染为 `˞/ɚ`；上方可继续附加音高符号。",
        "",
        "| 表层类 | 成员 | 标准 IPA | Yime 显示 |",
        "|---|---|---|---|",
    ]
    for class_id, row in audit["classes"].items():
        lines.append(
            f"| `{class_id}` | `{', '.join(row['members'])}` | `{row['surface_ipa']}` | `{row['surface_yime']}` |"
        )
    lines.extend(
        [
            "",
            "## 参数化分类",
            "",
            "- `ERHUA-NASAL-NG`：保留各成员呼音，基础主音同时加鼻化和卷舌特征，并复制到主音、末音两段；`ong/ueng` 与其余 `-ng` 韵母遵循同一结构规则。",
            "- 独立占位项 `ng` 不是本规则中的规范韵母，不自动生成儿化表层。",
            "- 其余单成员类：没有合流遗漏时维持已有人工标注。",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", type=Path, default=DEFAULT_DRAFT)
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = apply_surface_class_rules(args.draft, args.rules)
    audit = audit_surface_classes(args.draft, args.rules)
    if audit["mismatches"]:
        raise ValueError(f"儿化表层类仍不一致：{audit['mismatches']}")
    args.report.write_text(render_report(result, audit), encoding="utf-8", newline="\n")
    print(json.dumps({"result": result, "audit": audit}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
