import re
import os


RAW_YAML_FILENAME = "hanzi_pinyin_raw.yaml"
RAW_YAML_IMPORT_HINT = (
    "缺少 hanzi_pinyin_raw.yaml。该文件来自外部开源免费资源，"
    "本仓库不再跟踪；如需运行旧 raw-YAML 链，请先自行导入相关资源到当前目录。"
)


def remove_percent_and_save(input_file: str, output_file: str) -> None:
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"{RAW_YAML_IMPORT_HINT}\n期望路径: {input_file}")

    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    processed_lines: list[str] = []
    removed_count = 0
    no_tone_count = 0

    # 优化后的百分号匹配模式，精确匹配行尾
    percent_pattern = re.compile(r'\s*\d+\.?\d*%$')

    for line in lines:
        original_line = line
        line = line.strip()  # 去除首尾空白
        new_line = percent_pattern.sub('', line)

        if new_line != line:  # 只有当行被修改时才处理
            removed_count += 1
            processed_lines.append(new_line + '\n')
        else:
            processed_lines.append(original_line)  # 保留原行

    with open(output_file, 'w', encoding='utf-8') as f:
        f.writelines(processed_lines)

    print(f"共删除了{removed_count}行的行尾百分数")
    if no_tone_count > 0:
        print(f"发现{no_tone_count}行有不用数字标调的拼音")
    else:
        print("未发现不用数字标调的拼音")


if __name__ == "__main__":
    # 使用绝对路径
    base_dir = os.path.dirname(os.path.abspath(__file__))
    input_file = os.path.join(base_dir, RAW_YAML_FILENAME)
    output_file = os.path.join(base_dir, "hanzi_pinyin.yaml")
    try:
        remove_percent_and_save(input_file, output_file)
    except FileNotFoundError as exc:
        print(exc)
        raise SystemExit(1)
