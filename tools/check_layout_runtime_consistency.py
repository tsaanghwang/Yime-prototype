import argparse
import json
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Callable, cast


ResolvedLayoutBuilder = Callable[[object, object], dict[str, object]]

try:
    from tools.resolve_manual_key_layout import build_resolved_layout as _build_resolved_layout  # pyright: ignore[reportUnknownVariableType]
except ImportError:
    from resolve_manual_key_layout import build_resolved_layout as _build_resolved_layout  # pyright: ignore[reportUnknownVariableType]

build_resolved_layout = cast(ResolvedLayoutBuilder, _build_resolved_layout)


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LAYOUT = ROOT / "internal_data" / "manual_key_layout.json"
DEFAULT_LAYOUT_SYMBOLS = ROOT / "internal_data" / "key_to_symbol.json"
DEFAULT_BMP_PROJECTION = ROOT / "internal_data" / "bmp_pua_trial_projection.json"
DEFAULT_RESOLVED_LAYOUT = ROOT / "internal_data" / "manual_key_layout.resolved.json"
DEFAULT_RUNTIME_REPORT = ROOT / "internal_data" / "yinjie_runtime_key_symbol_mapping.json"
DEFAULT_SHOUYIN_RUNTIME = ROOT / "syllable" / "yinyuan" / "shouyin_codepoint.json"
DEFAULT_YINYUAN_RUNTIME = ROOT / "syllable" / "yinyuan" / "yinyuan_codepoint.json"


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def sort_yinyuan_ids(values: Iterable[str]) -> list[str]:
    def sort_key(item: str):
        return item[0], int(item[1:])

    return sorted(values, key=sort_key)


def derive_runtime_key_to_symbol(shouyin_runtime: dict[str, str], yueyin_runtime: dict[str, str]) -> dict[str, str]:
    runtime_key_to_symbol: dict[str, str] = {}
    for index, symbol in enumerate(shouyin_runtime.values(), start=1):
        runtime_key_to_symbol[f"N{index:02d}"] = symbol
    for index, symbol in enumerate(yueyin_runtime.values(), start=1):
        runtime_key_to_symbol[f"M{index:02d}"] = symbol
    return runtime_key_to_symbol


def load_bmp_projection_symbols(path: Path) -> dict[str, str]:
    payload_obj = load_json(path)
    if not isinstance(payload_obj, dict):
        raise ValueError("bmp_pua_trial_projection.json must be a JSON object")
    payload = cast(dict[str, object], payload_obj)

    used_mapping_obj = payload.get("used_mapping", {})
    if not isinstance(used_mapping_obj, dict):
        raise ValueError("bmp_pua_trial_projection.json missing used_mapping object")
    used_mapping = cast(dict[str, object], used_mapping_obj)

    symbols: dict[str, str] = {}
    for yinyuan_id, entry in used_mapping.items():
        if not isinstance(entry, dict):
            continue
        entry_dict = cast(dict[str, object], entry)
        char_obj = entry_dict.get("char")
        if isinstance(char_obj, str) and char_obj:
            symbols[yinyuan_id] = char_obj

    return symbols


def compare_key_maps(left_name: str, left_map: dict[str, str], right_name: str, right_map: dict[str, str]) -> list[str]:
    issues: list[str] = []

    left_keys = set(left_map)
    right_keys = set(right_map)

    missing_on_right = sort_yinyuan_ids(left_keys - right_keys)
    if missing_on_right:
        issues.append(
            f"{right_name} 缺少这些键位：{', '.join(missing_on_right)}。建议检查是否漏同步。"
        )

    missing_on_left = sort_yinyuan_ids(right_keys - left_keys)
    if missing_on_left:
        issues.append(
            f"{left_name} 缺少这些键位：{', '.join(missing_on_left)}。建议检查是否引用了额外或过期的符号。"
        )

    common_keys = sort_yinyuan_ids(left_keys & right_keys)
    for yinyuan_id in common_keys:
        if left_map[yinyuan_id] != right_map[yinyuan_id]:
            issues.append(
                f"Yinyuan ID {yinyuan_id} 在 {left_name} 与 {right_name} 中对应的私用区字符不同："
                f"{repr(left_map[yinyuan_id])} != {repr(right_map[yinyuan_id])}。"
            )

    return issues


def compare_runtime_internal_consistency(shouyin_runtime: dict[str, str], zaoyin_runtime: dict[str, str]) -> list[str]:
    issues: list[str] = []
    shouyin_names = list(shouyin_runtime)
    zaoyin_names = list(zaoyin_runtime)
    if shouyin_names != zaoyin_names:
        issues.append("`shouyin_codepoint.json` 与 `yinyuan_codepoint.json` 的首音标签顺序不一致。建议先修运行时源数据。"
        )

    for name in shouyin_names:
        if name in zaoyin_runtime and shouyin_runtime[name] != zaoyin_runtime[name]:
            issues.append(
                f"首音标签 {name} 在两份运行时文件里的字符不一致："
                f"{repr(shouyin_runtime[name])} != {repr(zaoyin_runtime[name])}。"
            )
    return issues


def collect_layout_assignments(resolved_layout: dict[str, object]) -> tuple[dict[str, dict[str, object]], list[str]]:
    assignments: dict[str, dict[str, object]] = {}
    issues: list[str] = []

    layers_obj = resolved_layout.get("layers", [])
    if not isinstance(layers_obj, list):
        issues.append("resolved layout 的 layers 字段类型错误，预期为数组。")
        return assignments, issues
    layers = cast(list[object], layers_obj)

    for raw_item in layers:
        if not isinstance(raw_item, dict):
            continue

        item = cast(dict[str, object], raw_item)
        yinyuan_id_obj = item.get("yinyuan_id")
        if not isinstance(yinyuan_id_obj, str):
            continue
        yinyuan_id = yinyuan_id_obj

        if yinyuan_id in assignments:
            previous = assignments[yinyuan_id]
            issues.append(
                f"Yinyuan ID {yinyuan_id} 在布局中重复分配："
                f"{previous['output_layer']}:{previous['physical_key']} 和 {item['output_layer']}:{item['physical_key']}。"
            )
            continue
        assignments[yinyuan_id] = item

    return assignments, issues


def compare_layout_assignments(
    assignments: dict[str, dict[str, object]],
    runtime_key_to_symbol: dict[str, str],
    bmp_projection_symbols: dict[str, str],
) -> tuple[list[str], list[str]]:
    issues: list[str] = []
    notes: list[str] = []

    for yinyuan_id in sort_yinyuan_ids(assignments):
        item = assignments[yinyuan_id]
        if yinyuan_id not in runtime_key_to_symbol:
            issues.append(
                f"布局中使用了 Yinyuan ID {yinyuan_id}，但运行时生成侧没有这个 ID。建议检查是否写入了不存在的音元。"
            )
            continue

        if yinyuan_id not in bmp_projection_symbols:
            issues.append(
                f"布局中使用了 Yinyuan ID {yinyuan_id}，但 BMP projection 中没有这个 ID。建议先更新 bmp_pua_trial_projection.json。"
            )
            continue

        runtime_symbol = runtime_key_to_symbol[yinyuan_id]
        projected_layout_symbol = bmp_projection_symbols[yinyuan_id]
        if projected_layout_symbol != runtime_symbol:
            issues.append(
                f"Yinyuan ID {yinyuan_id} 当前落在 {item['output_layer']}:{item['physical_key']}，"
                f"但该 ID 的 BMP 投影字符 {repr(projected_layout_symbol)} 与运行时字符 {repr(runtime_symbol)} 不一致。"
            )

    unplaced = sort_yinyuan_ids(set(runtime_key_to_symbol) - set(assignments))
    if unplaced:
        notes.append(
            "以下运行时码元当前还没有进入物理布局："
            f"{', '.join(unplaced)}。这不一定是错误，但建议确认这是不是有意保留。"
        )

    return issues, notes


def compare_artifact(name: str, expected_map: dict[str, str], artifact_path: Path) -> list[str]:
    if not artifact_path.exists():
        return [f"{name} 文件不存在：{artifact_path}。建议重新生成。"]

    artifact_data = load_json(artifact_path)
    if name == "runtime_report":
        artifact_map = artifact_data.get("key_to_symbol", {})
    else:
        artifact_map = {
            item["yinyuan_id"]: item.get("symbol_char")
            for item in artifact_data.get("layers", [])
            if item.get("yinyuan_id") is not None
        }

    if artifact_map != expected_map:
        return [f"{artifact_path.name} 看起来不是最新结果。建议重新生成后再继续检查。"]
    return []


def print_section(title: str, messages: list[str]) -> None:
    if not messages:
        return

    print(title)
    for message in messages:
        print(f"- {message}")
    print()


def classify_status(issues: list[str], notes: list[str]) -> str:
    if issues:
        return "error"
    if notes:
        return "warning"
    return "ok"


def build_json_payload(
    issues: list[str],
    notes: list[str],
    runtime_key_to_symbol: dict[str, str],
    assignments: dict[str, dict[str, object]],
    args: argparse.Namespace,
) -> dict[str, object]:
    status = classify_status(issues, notes)
    return {
        "ok": status == "ok",
        "status": status,
        "summary": {
            "issue_count": len(issues),
            "note_count": len(notes),
            "runtime_symbol_count": len(runtime_key_to_symbol),
            "placed_symbol_count": len(assignments),
            "unplaced_symbol_count": len(set(runtime_key_to_symbol) - set(assignments)),
        },
        "issues": issues,
        "notes": notes,
        "paths": {
            "layout": str(args.layout),
            "symbols": str(args.symbols),
            "bmp_projection": str(args.bmp_projection),
            "resolved_layout": str(args.resolved_layout),
            "runtime_report": str(args.runtime_report),
            "shouyin_runtime": str(args.shouyin_runtime),
            "yinyuan_runtime": str(args.yinyuan_runtime),
        },
    }


def emit_json_payload(payload: dict[str, object], output_path: Path | None) -> None:
    json_text = json.dumps(payload, ensure_ascii=False, indent=2)
    if output_path is None:
        print(json_text)
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        handle.write(json_text)
        handle.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check whether the layout side and runtime PUA-generation side are still consistent."
    )
    parser.add_argument("--layout", type=Path, default=DEFAULT_LAYOUT)
    parser.add_argument("--symbols", type=Path, default=DEFAULT_LAYOUT_SYMBOLS)
    parser.add_argument("--bmp-projection", type=Path, default=DEFAULT_BMP_PROJECTION)
    parser.add_argument("--resolved-layout", type=Path, default=DEFAULT_RESOLVED_LAYOUT)
    parser.add_argument("--runtime-report", type=Path, default=DEFAULT_RUNTIME_REPORT)
    parser.add_argument("--shouyin-runtime", type=Path, default=DEFAULT_SHOUYIN_RUNTIME)
    parser.add_argument("--yinyuan-runtime", type=Path, default=DEFAULT_YINYUAN_RUNTIME)
    parser.add_argument(
        "--ignore-stale-artifacts",
        action="store_true",
        help="Do not warn when cached artifact files differ from freshly derived data.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of human-readable text.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=None,
        help="Write the JSON result to the given file path. Can be used with or without --json.",
    )
    args = parser.parse_args()

    layout_data = load_json(args.layout)
    layout_key_to_symbol = load_json(args.symbols)
    bmp_projection_symbols = load_bmp_projection_symbols(args.bmp_projection)
    resolved_layout = build_resolved_layout(layout_data, layout_key_to_symbol)

    shouyin_data = load_json(args.shouyin_runtime)
    yinyuan_data = load_json(args.yinyuan_runtime)

    shouyin_runtime = shouyin_data.get("首音", {})
    zaoyin_runtime = yinyuan_data.get("zaoyin", {})
    yueyin_runtime = yinyuan_data.get("yueyin", {})

    runtime_key_to_symbol = derive_runtime_key_to_symbol(shouyin_runtime, yueyin_runtime)
    assignments, assignment_issues = collect_layout_assignments(resolved_layout)

    issues: list[str] = []
    notes: list[str] = []

    issues.extend(compare_runtime_internal_consistency(shouyin_runtime, zaoyin_runtime))
    issues.extend(compare_key_maps("运行时生成侧", runtime_key_to_symbol, "BMP 投影表", bmp_projection_symbols))
    layout_issues, layout_notes = compare_layout_assignments(assignments, runtime_key_to_symbol, bmp_projection_symbols)
    issues.extend(assignment_issues)
    issues.extend(layout_issues)
    notes.extend(layout_notes)

    if not args.ignore_stale_artifacts:
        issues.extend(compare_artifact("resolved_layout", assignments_to_map(assignments), args.resolved_layout))
        issues.extend(compare_artifact("runtime_report", runtime_key_to_symbol, args.runtime_report))

    status = classify_status(issues, notes)

    if args.json or args.json_output is not None:
        payload = build_json_payload(issues, notes, runtime_key_to_symbol, assignments, args)
        emit_json_payload(payload, args.json_output)
        sys.exit(1 if status == "error" else 0)

    if status == "error":
        print("请留意：布局侧与私用区字符生成侧发现了需要复查的地方。")
        print()
        print_section("建议优先处理：", issues)
        if notes:
            print_section("补充说明：", notes)
        sys.exit(1)

    if status == "warning":
        print("目前未发现布局侧与私用区字符生成侧的硬性不一致，但有几项提示可留意。")
        print()
        print_section("补充说明：", notes)
        return

    print("目前未发现布局侧与私用区字符生成侧的硬性不一致。")
    if notes:
        print()
        print_section("补充说明：", notes)


def assignments_to_map(assignments: dict[str, dict[str, object]]) -> dict[str, str]:
    return {
        yinyuan_id: symbol_char if isinstance(symbol_char := item.get("symbol_char"), str) else ""
        for yinyuan_id, item in assignments.items()
    }


if __name__ == "__main__":
    main()
