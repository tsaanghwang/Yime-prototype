"""
首音分析
功能：确定首音音标和划分首音类别。
"""
import json
from pathlib import Path
from typing import Any, cast

from syllable.analysis.zaoyin_yinyuan import ClearZaoyin, VoicedZaoyin
from syllable.analysis.syllable_splitter import SyllableSplitter


SYLLABLE_DIR = Path(__file__).resolve().parents[2] / "syllable"
YINYUAN_DIR = SYLLABLE_DIR / "yinyuan"


# 根据语音事实预定浊音列表, 双隔音符表示浊零声母
VOICED_INITIALS = {
    'm', 'n', 'l', 'r', 'w', 'y', "''"
}


def map_shouyin_to_ipa(initial: str | None = None) -> dict[str, list[str]] | list[str]:
    """
    把首音映射到音标
    参数:
        initial: (可选)首音字符串，如果为None则返回完整映射字典
    返回:
        对应的音标列表或完整映射字典
    """
    try:
        # 尝试从配置文件中读取映射关系
        with (YINYUAN_DIR / 'initial_ipa.json').open('r', encoding='utf-8') as f:
            loaded = cast(dict[str, Any], json.load(f))
            initial_ipa_mapping = cast(dict[str, list[str]], loaded.get('initial', {}))
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        # 如果文件不存在或格式不正确，使用内置的默认映射
        initial_ipa_mapping: dict[str, list[str]] = {
            'b': ['p'],
            'p': ['pʰ'],
            'f': ['f'],
            'm': ['m'],
            'd': ['t'],
            't': ['tʰ'],
            'l': ['l'],
            'n': ['n'],
            'g': ['k'],
            'k': ['kʰ'],
            'h': ['x'],
            'z': ['ʦ'],
            'c': ['ʦʰ'],
            's': ['s'],
            'zh': ['tʂ'],
            'ch': ['tʂʰ'],
            'sh': ['ʂ'],
            'r': ['ʐ'],
            'j': ['tɕ'],
            'q': ['tɕʰ'],
            'x': ['ɕ'],
            'w': ['w'],
            'y': ['j'],
            "''": ['ʔ']
        }

    if initial is None:
        return initial_ipa_mapping
    return initial_ipa_mapping.get(initial, [])


def create_uncertain_pitch_pianyin() -> dict[str, dict[str, list[str]]]:
    """创建噪音对象并分类为清音和浊音"""
    voiceless: dict[str, list[str]] = {}
    voiced: dict[str, list[str]] = {}

    # 获取所有可能的声母
    initial_ipa_mapping = cast(dict[str, list[str]], map_shouyin_to_ipa())
    all_initials = VOICED_INITIALS.union(set(initial_ipa_mapping.keys()))

    for initial in all_initials:
        ipa_list = initial_ipa_mapping.get(initial, [])
        # 判断是否为浊音
        if initial in VOICED_INITIALS:
            zaoyin = VoicedZaoyin(quality=initial)
            if zaoyin.is_valid():
                voiced[initial] = ipa_list
        else:
            zaoyin = ClearZaoyin(quality=initial)
            if zaoyin.is_valid():
                voiceless[initial] = ipa_list

    return {"unpitched_pianyin": voiceless, "unstable_pitch_pianyin": voiced}

def merge_shouyin_data():
    """
    生成并合并首音数据
    1. 调用生成首音数据
    2. 用map_shouyin_to_ipa中的音标列表替换匹配的声母音标
    """
    # 获取所有可能的声母
    initial_ipa_mapping = cast(dict[str, list[str]], map_shouyin_to_ipa())
    initials = VOICED_INITIALS.union(set(initial_ipa_mapping.keys()))

    # 生成原始首音数据 - 创建一个模拟的拼音字典，只包含声母
    mock_pinyin_data = {initial: initial for initial in initials}
    shouyin_data = cast(dict[str, list[str]], SyllableSplitter.generate_shouyin_data(mock_pinyin_data))

    # 替换匹配的声母音标，保持原始列表形式
    for initial in initials:
        ipa_list = initial_ipa_mapping.get(initial, [])
        if initial in shouyin_data:
            shouyin_data[initial] = ipa_list

    return shouyin_data


def main():
    """主函数，执行首音分析流程"""
    try:
        # 1. 生成并合并首音数据
        merge_shouyin_data()

        # 2. 验证噪音类数据并写入兼容旧格式的字段
        classified_zaoyin = create_uncertain_pitch_pianyin()

        # 3. 读取现有的噪音声母文件

        pianyin_initial_path = YINYUAN_DIR / 'pianyin_initial.json'

        with pianyin_initial_path.open('r', encoding='utf-8') as f:
            pianyin_initial = cast(dict[str, Any], json.load(f))

        name = str(pianyin_initial.get("name", ""))
        description = str(pianyin_initial.get("description", ""))
        note = str(pianyin_initial.get("note", ""))

        # 4. 更新噪音部分并保留元数据
        output: dict[str, object] = {
            "name": name,
            "description": description,
            "note": note,
            "uncertain_pitch_pianyin": classified_zaoyin
        }

        # 5. 保存结果
        with pianyin_initial_path.open('w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        print(f"首音和噪音声母映射已成功生成并更新在: {pianyin_initial_path}")
    except Exception as e:
        print(f"处理过程中发生错误: {str(e)}")


if __name__ == '__main__':
    main()
