import json
from pathlib import Path
from typing import Any

from syllable.analysis.final_ipa_registry import (
    require_complete_final_ipa_registry,
    sync_final_ipa_registry,
)

"""将数字标调的干音数据转换为带声调标记和IPA的格式"""

SYLLABLE_DIR = Path(__file__).resolve().parents[2] / "syllable"
YINYUAN_DIR = SYLLABLE_DIR / "yinyuan"
DERIVED_OUTPUT_DIR = Path(__file__).resolve().parents[2] / "internal_data" / "yinyuan_derived"

# 从唯一主表派生视图读取韵母与国际音标（IPA）的映射
def load_final_styles() -> dict[str, str]:
    """加载韵母与IPA的映射关系"""
    final_styles_path = YINYUAN_DIR / "final_styles.json"
    with open(final_styles_path, "r", encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)

    # 构建韵母到IPA的映射字典
    ipa_map: dict[str, str] = {}
    finals: dict[str, dict[str, dict[str, str]]] = data["finals"]
    for category in finals.values():
        for final, info in category.items():
            # 处理特殊韵母"_i"的IPA值（ɿ/ʅ）
            if final == "_i":
                ipa_map[final] = info["ipa"]
            else:
                ipa_map[final] = info["ipa"]
    return ipa_map


# 数字调号到声调标记的映射
TONE_MARK_MAP = {
    "1": "̄",  # macron
    "2": "́",  # acute
    "3": "̌",  # caron
    "4": "̀",  # grave
    "5": "",   # no mark
}


def get_pinyin(base: str, tone_num: str) -> str:
    # 处理下划线前缀
    if base.startswith("_"):
        base = base[1:]
    mark = TONE_MARK_MAP.get(tone_num, "")
    return base + mark


def get_ipa(base: str, tone_num: str, ipa_map: dict[str, str] | None = None) -> str:
    """获取韵母的IPA表示（含声调）"""
    # 特殊处理带下划线的韵母（如"_i"）
    base_key = base if base.startswith("_") else base.lstrip("_")
    resolved_map = ipa_map if ipa_map is not None else load_final_styles()
    if base_key not in resolved_map:
        raise KeyError(f"韵母 {base_key!r} 缺少 IPA；请先同步韵母 IPA 主表")
    ipa_base = str(resolved_map[base_key])
    tone_ipa: dict[str, str] = {
        "1": "˥˥˥",    # 降调
        "2": "˧˦˥",   # 升调
        "3": "˨˩˨",  # 低调
        "4": "˥˦˩",   # 降调
        "5": "˦˦˦",     # 中性调(轻声调)
    }

    # 特殊处理 "_i" 韵母，返回两种变体
    if base_key == "_i":
        return f"ɿ{tone_ipa.get(tone_num, '')}/ʅ{tone_ipa.get(tone_num, '')}"

    return ipa_base + tone_ipa.get(tone_num, "")


def enhance_ganyin(input_path: Path, output_path: Path) -> None:
    sync_result = sync_final_ipa_registry(ganyin_path=input_path)
    require_complete_final_ipa_registry(sync_result)
    ipa_map = load_final_styles()

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    enhanced = {}
    for category, items in data["ganyin"].items():
        enhanced[category] = {}
        for key, pinyin in items.items():
            # key 例: "_i1"
            if key[-1].isdigit():
                base = key[:-1]
                tone_num = key[-1]
            else:
                base = key
                tone_num = "5"
            enhanced[category][key] = {
                "ime": key,
                "pinyin": pinyin,
                "ipa": get_ipa(base, tone_num, ipa_map)
            }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(enhanced, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    input_path = YINYUAN_DIR / "ganyin.json"
    output_path = DERIVED_OUTPUT_DIR / 'ganyin_enhanced.json'
    enhance_ganyin(input_path, output_path)

    print(f"转换完成，结果已保存到 {output_path}")
