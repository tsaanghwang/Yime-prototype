"""Synchronize the editable final IPA registry with attested ganyin data."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from syllable.analysis.final_ipa_registry import sync_final_ipa_registry


def main() -> int:
    parser = argparse.ArgumentParser(
        description="以当前析出的韵母集合校准 IPA 主表，并派生 final_styles.json。"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="只检查，不改写文件；不同步或存在 IPA 占位符时返回失败。",
    )
    args = parser.parse_args()

    result = sync_final_ipa_registry(write=not args.check)
    print(f"实际韵母：{result.actual_count}")
    print(f"新增韵母：{', '.join(result.added) if result.added else '无'}")
    print(f"删除多余韵母：{', '.join(result.removed) if result.removed else '无'}")
    print(f"待填写 IPA：{', '.join(result.placeholders) if result.placeholders else '无'}")
    if result.migrated_legacy_schema:
        print("已把旧 IPA→韵母表转换为韵母→IPA 主表。")

    if args.check and (
        result.registry_changed
        or result.final_styles_changed
        or result.placeholders
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
