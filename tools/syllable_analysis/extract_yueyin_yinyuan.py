"""
析取乐音类音元 - 使用具体的音元类生成音元数据文件
"""

import json
from pathlib import Path

from syllable.analysis.yueyin_mapper import YueyinMapper


SYLLABLE_DIR = Path(__file__).resolve().parents[2] / "syllable"
YINYUAN_DIR = SYLLABLE_DIR / "yinyuan"


def extract_yueyin_yinyuan():
    """生成乐音类音元数据文件"""

    # 输入输出文件路径
    input_path = YINYUAN_DIR / 'pitched_pianyin.json'
    output_mid_high_median_model_path = YINYUAN_DIR / \
        'pitched_yinyuan_of_mid_high_median_model.json'
    output_mid_level_median_model_path = YINYUAN_DIR / \
        'pitched_yinyuan_of_mid_level_median_model.json'

    # 读取输入数据
    with open(input_path, 'r', encoding='utf-8') as f:
        input_data = json.load(f)

    # 转换数据格式: {"key": "value"} -> {"key": ["quality", "pitch"]}
    converted_data = {key: [key[:-1], key[-1]] for key in input_data.keys()}

    mapper = YueyinMapper(YINYUAN_DIR / 'variables_of_attributes.json')

    # 处理数据 - 以归并器为唯一真源
    mid_high_median_model = mapper.group_symbols(
        converted_data,
        model='mid_high_median_model',
    )
    output_mid_level_median_model = mapper.group_symbols(
        converted_data,
        model='mid_level_median_model',
    )

    # 保存结果
    with open(output_mid_high_median_model_path, 'w', encoding='utf-8') as f:
        json.dump(mid_high_median_model, f, ensure_ascii=False, indent=2)

    with open(output_mid_level_median_model_path, 'w', encoding='utf-8') as f:
        json.dump(output_mid_level_median_model,
                  f, ensure_ascii=False, indent=2)

    print("处理完成，结果已保存到:")
    print(f"- {output_mid_high_median_model_path}")
    print(f"- {output_mid_level_median_model_path}")


if __name__ == '__main__':
    extract_yueyin_yinyuan()
