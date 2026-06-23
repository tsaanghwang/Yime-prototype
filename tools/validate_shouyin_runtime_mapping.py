import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, cast


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = ROOT / "syllable" / "yinyuan" / "zaoyin_yinyuan_enhanced.json"
DEFAULT_SHOUYIN_RUNTIME = ROOT / "syllable" / "yinyuan" / "shouyin_codepoint.json"
DEFAULT_YINYUAN_RUNTIME = ROOT / "syllable" / "yinyuan" / "yinyuan_codepoint.json"


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data, dict):
        return cast(dict[str, Any], data)
    return {}


def collect_duplicates(values: dict[str, str], label: str) -> list[str]:
    reverse: dict[str, list[str]] = defaultdict(list)
    for key, value in values.items():
        reverse[value].append(key)

    issues: list[str] = []
    for value, keys in sorted(reverse.items()):
        if len(keys) > 1:
            issues.append(
                f"duplicate {label}: {value!r} is shared by {', '.join(sorted(keys))}"
            )
    return issues


def validate_shouyin_mapping(
    source_path: Path,
    shouyin_runtime_path: Path,
    yinyuan_runtime_path: Path,
) -> list[str]:
    issues: list[str] = []

    source_data = load_json(source_path)
    entries_obj = source_data.get("entries", {})
    if not isinstance(entries_obj, dict) or not entries_obj:
        return [f"source file has no usable entries: {source_path}"]
    entries: dict[str, Any] = cast(dict[str, Any], entries_obj)

    source_semantic_codes: dict[str, str] = {}
    source_runtime_chars: dict[str, str] = {}

    for shouyin, entry_obj in entries.items():

        if not isinstance(entry_obj, dict):
            issues.append(f"source entry is not an object: {shouyin}")
            continue
        entry: dict[str, Any] = cast(dict[str, Any], entry_obj)

        semantic_code_obj = entry.get("semantic_code", "")
        runtime_char_obj = entry.get("runtime_char", "")
        ipa_obj = entry.get("ipa", [])

        semantic_code = semantic_code_obj if isinstance(semantic_code_obj, str) else ""
        runtime_char = runtime_char_obj if isinstance(runtime_char_obj, str) else ""

        if not semantic_code:
            issues.append(f"missing semantic_code: {shouyin}")
        else:
            source_semantic_codes[shouyin] = semantic_code

        if not runtime_char:
            issues.append(f"missing runtime_char: {shouyin}")
        else:
            source_runtime_chars[shouyin] = runtime_char

        if not isinstance(ipa_obj, list):
            issues.append(f"ipa must be a list: {shouyin}")

    issues.extend(collect_duplicates(source_semantic_codes, "semantic_code"))
    issues.extend(collect_duplicates(source_runtime_chars, "runtime_char"))

    shouyin_runtime_obj = load_json(shouyin_runtime_path).get("首音", {})
    if not isinstance(shouyin_runtime_obj, dict):
        issues.append(f"runtime file is missing 首音 mapping: {shouyin_runtime_path}")
        shouyin_runtime_obj = {}
    shouyin_runtime: dict[str, str] = {}
    shouyin_runtime_items = cast(dict[Any, Any], shouyin_runtime_obj)
    for key_obj, value_obj in shouyin_runtime_items.items():
        if isinstance(key_obj, str) and isinstance(value_obj, str):
            shouyin_runtime[key_obj] = value_obj

    yinyuan_runtime_obj = load_json(yinyuan_runtime_path).get("zaoyin", {})
    if not isinstance(yinyuan_runtime_obj, dict):
        issues.append(f"runtime file is missing zaoyin mapping: {yinyuan_runtime_path}")
        yinyuan_runtime_obj = {}
    yinyuan_runtime: dict[str, str] = {}
    yinyuan_runtime_items = cast(dict[Any, Any], yinyuan_runtime_obj)
    for key_obj, value_obj in yinyuan_runtime_items.items():
        if isinstance(key_obj, str) and isinstance(value_obj, str):
            yinyuan_runtime[key_obj] = value_obj

    source_keys = set(source_runtime_chars)
    shouyin_keys = set(shouyin_runtime)
    yinyuan_keys = set(yinyuan_runtime)

    missing_in_shouyin = sorted(source_keys - shouyin_keys)
    if missing_in_shouyin:
        issues.append(
            "missing keys in shouyin_codepoint.json: " + ", ".join(missing_in_shouyin)
        )

    missing_in_yinyuan = sorted(source_keys - yinyuan_keys)
    if missing_in_yinyuan:
        issues.append(
            "missing keys in yinyuan_codepoint.json.zaoyin: " + ", ".join(missing_in_yinyuan)
        )

    extra_in_shouyin = sorted(shouyin_keys - source_keys)
    if extra_in_shouyin:
        issues.append(
            "extra keys in shouyin_codepoint.json: " + ", ".join(extra_in_shouyin)
        )

    extra_in_yinyuan = sorted(yinyuan_keys - source_keys)
    if extra_in_yinyuan:
        issues.append(
            "extra keys in yinyuan_codepoint.json.zaoyin: " + ", ".join(extra_in_yinyuan)
        )

    common_keys = sorted(source_keys & shouyin_keys & yinyuan_keys)
    for shouyin in common_keys:
        source_char = source_runtime_chars[shouyin]
        shouyin_char = shouyin_runtime[shouyin]
        yinyuan_char = yinyuan_runtime[shouyin]

        if source_char != shouyin_char:
            issues.append(
                f"source/runtime mismatch for {shouyin}: source={source_char!r}, shouyin_runtime={shouyin_char!r}"
            )
        if source_char != yinyuan_char:
            issues.append(
                f"source/runtime mismatch for {shouyin}: source={source_char!r}, yinyuan_runtime={yinyuan_char!r}"
            )
        if shouyin_char != yinyuan_char:
            issues.append(
                f"runtime/runtime mismatch for {shouyin}: shouyin_runtime={shouyin_char!r}, yinyuan_runtime={yinyuan_char!r}"
            )

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate shouyin source entries against runtime mapping artifacts."
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--shouyin-runtime", type=Path, default=DEFAULT_SHOUYIN_RUNTIME)
    parser.add_argument("--yinyuan-runtime", type=Path, default=DEFAULT_YINYUAN_RUNTIME)
    args = parser.parse_args()

    issues = validate_shouyin_mapping(
        source_path=args.source,
        shouyin_runtime_path=args.shouyin_runtime,
        yinyuan_runtime_path=args.yinyuan_runtime,
    )

    if issues:
        print("shouyin mapping validation failed")
        for issue in issues:
            print(f"- {issue}")
        return 1

    print("shouyin mapping validation passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
