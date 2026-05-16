import json
from pathlib import Path


def reverse_key_value_pairs(input_path, output_path):
    """
    反转 JSON 文件的键值对，所有值统一用列表表示。
    若有多个键对应同一个值，则值对应一个键列表。

    Args:
        input_path: 输入 JSON 文件路径
        output_path: 输出 JSON 文件路径

    Returns:
        tuple: (是否成功, 原始键值对数量, 新键值对数量, 合并项数量)
    """
    try:
        with open(input_path, 'r', encoding='utf-8') as handle:
            data = json.load(handle)

        original_count = len(data)
        reversed_data = {}
        merge_count = 0

        for key, value in data.items():
            if value in reversed_data:
                reversed_data[value].append(key)
                merge_count += 1
            else:
                reversed_data[value] = [key]

        new_count = len(reversed_data)

        output_dir = Path(output_path).parent
        output_dir.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as handle:
            json.dump(reversed_data, handle, ensure_ascii=False, indent=2)

        return True, original_count, new_count, merge_count

    except Exception as exc:
        print(f"Error: {str(exc)}")
        return False, 0, 0, 0
