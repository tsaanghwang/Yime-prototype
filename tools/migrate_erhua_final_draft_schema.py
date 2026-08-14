#!/usr/bin/env python3
"""Migrate the research-only erhua draft to structured segment features."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from syllable.analysis.erhua_final_review import (  # noqa: E402
    FEATURE_NAMES,
    SEGMENT_NAMES,
    ErhuaFinalDraftStore,
    render_surface_segments,
)


DEFAULT_DRAFT = ROOT / "external_data" / "tmp" / "final_styles_erhua_draft.json"
DEFAULT_DECOMPOSITION = (
    ROOT
    / "internal_data"
    / "yinyuan_derived"
    / "ganyin_to_pianyin_sequence.json"
)
DEFAULT_REPORT = ROOT / "external_data" / "tmp" / "final_styles_erhua_draft_audit.md"


def audit(store: ErhuaFinalDraftStore) -> dict[str, object]:
    items = store.load_items()
    decisions = Counter(item.decision for item in items)
    feature_counts = Counter()
    legacy_fields: list[str] = []
    display_markers_in_quality: list[str] = []
    rendering_mismatches: list[str] = []
    no_source: list[str] = []
    merged_sources: dict[str, list[str]] = {}

    for item in items:
        review = item.review
        for field in ("rhotic_positions", "nasalized_positions"):
            if field in review:
                legacy_fields.append(f"{item.final}.{field}")
        segments = review.get("surface_segments") or {}
        for position in SEGMENT_NAMES:
            segment = segments[position]
            quality = str(segment["quality"])
            if any(marker in quality for marker in ("ɚ", "ɝ", "˞", "᷊", "ͬ", "̃")):
                display_markers_in_quality.append(f"{item.final}.{position}")
            for feature in FEATURE_NAMES:
                if segment["features"][feature]:
                    feature_counts[feature] += 1
        if review.get("surface_ipa") != render_surface_segments(segments):
            rendering_mismatches.append(item.final)
        if not item.source_annotations:
            no_source.append(item.final)
        source_bases = sorted(
            {
                str(source.get("source_base_final"))
                for source in item.source_annotations
                if source.get("source_base_final")
            }
        )
        if len(source_bases) > 1:
            merged_sources[item.final] = source_bases

    return {
        "items": len(items),
        "decisions": dict(decisions),
        "feature_counts": dict(feature_counts),
        "legacy_fields": legacy_fields,
        "display_markers_in_quality": display_markers_in_quality,
        "rendering_mismatches": rendering_mismatches,
        "entries_without_psc_source": no_source,
        "merged_source_base_finals": merged_sources,
    }


def render_report(result: dict[str, object], migration: dict[str, int]) -> str:
    return f"""# 儿化标注草稿结构审计

- 范围：研究草稿、校对模型和显示层；未修改正式音元源、布局或运行时。
- 韵母条目：{result['items']}；复核状态：{result['decisions']}。
- 本次迁移：{migration}。

## 数据结构结论

- 三段位置固定为 `呼音 / 主音 / 末音`。
- 每段保存 `quality` 与并行的 `features.rhotic / features.nasalized`。
- `ɚ/ɝ/˞/᷊/̃` 只由显示器派生，不得存入 `quality`，也不增加片音位置。
- `᷊`（U+1DCA，COMBINING LATIN SMALL LETTER R BELOW）定义为 Yime 项目显示附标：只表示前一片音的 `rhotic=true`；不是来源 IPA 转录。它位于字母下方，上方可继续附加音高符号。
- 旧显示附标 `ͬ`（U+036C）只用于迁移兼容，不再生成。
- 旧字段残留：{result['legacy_fields'] or '无'}。
- 音质字段中的显示符号残留：{result['display_markers_in_quality'] or '无'}。
- `surface_ipa` 派生不一致：{result['rendering_mismatches'] or '无'}。
- 特征位置计数：{result['feature_counts']}。

此前 `rhotic_positions` 与显示字符不一致的问题已由结构迁移消除：卷舌和鼻化现在归属于各自的固定片音，
不再另存容易失配的位置清单。

## 尚未解决的语音建模问题

1. `ong/ueng` 保持为不同的来源分析形式；本草稿不预设 `uong` 合并层。
2. `v/ve/vn/van/ue` 不进入草稿；只有外部协议确有需要时才在边界转换。
3. `m/n/ng/ê` 无 PSC 儿化类别；`er` 是独立音节，不是儿化基式。
4. 单元音、`i/ü` 和鼻化韵的卷舌动程仍是工作假设，不因本次结构迁移自动改值。

### 无 PSC 儿化来源

{json.dumps(result['entries_without_psc_source'], ensure_ascii=False, indent=2)}

### 合并了不同来源韵母的内部条目

{json.dumps(result['merged_source_base_finals'], ensure_ascii=False, indent=2)}
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", type=Path, default=DEFAULT_DRAFT)
    parser.add_argument("--decomposition", type=Path, default=DEFAULT_DECOMPOSITION)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    store = ErhuaFinalDraftStore(args.draft, args.decomposition)
    removed_deferred_finals = store.prune_deferred_internal_finals()
    migration = store.migrate_surface_segment_schema()
    migration["removed_deferred_finals"] = len(removed_deferred_finals)
    result = audit(store)
    if result["legacy_fields"] or result["display_markers_in_quality"] or result["rendering_mismatches"]:
        raise ValueError("儿化草稿结构迁移后的审计门禁失败")
    args.report.write_text(render_report(result, migration), encoding="utf-8", newline="\n")
    print(json.dumps({"migration": migration, "audit": result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
