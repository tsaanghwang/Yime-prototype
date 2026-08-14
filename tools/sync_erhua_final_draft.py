"""Synchronize canonical final IPA and base segments into the erhua draft."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from syllable.analysis.erhua_draft_sync import sync_erhua_draft_foundations


def _display(values: tuple[str, ...]) -> str:
    return "、".join(values) if values else "无"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="非破坏性同步儿化草稿的基础韵母 IPA 与三段音质。"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="只检查、不写入；基础层存在漂移时返回失败。",
    )
    args = parser.parse_args()

    result = sync_erhua_draft_foundations(write=not args.check)
    print(f"活动韵母：{result.actual_count}")
    print(f"新增：{_display(result.added)}")
    print(f"移入归档：{_display(result.archived)}")
    print(f"分类移动：{_display(result.moved_categories)}")
    print(f"基础 IPA 更新：{_display(result.ipa_changed)}")
    print(f"基础三段更新：{_display(result.base_segments_changed)}")
    print(f"建议复看儿化表层：{_display(result.surface_review_required)}")
    print("人工儿化表层、来源证据、备注和复核决定：保留")
    return 1 if args.check and result.changed else 0


if __name__ == "__main__":
    raise SystemExit(main())
