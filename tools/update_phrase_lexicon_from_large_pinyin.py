from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
YIME_DIR = ROOT / "yime"
REBUILD_SOURCE_SCRIPT = ROOT / "internal_data" / "pinyin_source_db" / "rebuild_pinyin_assets.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "从统一来源证据库重建 Yime 当前主线词库。"
            "流程：统一来源库 -> 音节编码 -> prototype tables -> runtime。"
            "默认真正执行；可先用 --dry-run 看将要跑哪些命令。"
        )
    )
    parser.add_argument("--wanxiang-root", default=str(ROOT.parent / "RIME-LMDG"))
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="执行后续子命令的 Python，可显式指定虚拟环境解释器。",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印将执行的命令，不真正写入数据库或导出 runtime。",
    )
    parser.add_argument(
        "--skip-source-build",
        action="store_true",
        help="复用已经生成的统一来源库。",
    )
    parser.add_argument(
        "--skip-runtime-apply",
        action="store_true",
        help="跳过 refresh_runtime_yime_codes.py --apply；用于只更新 source/prototype 层。",
    )
    return parser.parse_args()


def build_commands(args: argparse.Namespace) -> list[tuple[str, list[str]]]:
    commands: list[tuple[str, list[str]]] = [
        (
            "rebuild-unified-source",
            [
                args.python,
                str(REBUILD_SOURCE_SCRIPT),
                "--wanxiang-root",
                args.wanxiang_root,
            ],
        )
    ]
    if args.skip_source_build:
        commands[0][1].append("--skip-bundle-build")
    commands.extend(
        [
            (
                "import-single-char",
                [args.python, "-m", "yime.import_danzi_into_prototype_tables"],
            ),
            (
                "import-phrase",
                [args.python, "-m", "yime.import_duozi_into_prototype_tables"],
            ),
        ]
    )
    if not args.skip_runtime_apply:
        commands.append(
            (
                "refresh-runtime",
                [args.python, "-m", "yime.refresh_runtime_yime_codes", "--apply"],
            )
        )
    return commands


def validate_script_paths() -> None:
    required_paths = [
        REBUILD_SOURCE_SCRIPT,
    ]

    missing_paths = [path for path in required_paths if not path.exists()]
    if missing_paths:
        missing_display = ", ".join(str(path) for path in missing_paths)
        raise FileNotFoundError(f"required script path not found: {missing_display}")


def print_plan(commands: list[tuple[str, list[str]]]) -> None:
    print("workspace_root=", ROOT, sep="")
    for step_name, command in commands:
        quoted = " ".join(shlex.quote(part) for part in command)
        print(f"[{step_name}] {quoted}")


def main() -> int:
    args = parse_args()
    validate_script_paths()

    commands = build_commands(args)
    print_plan(commands)
    if args.dry_run:
        print("dry_run=true")
        return 0

    for step_name, command in commands:
        print(f"running={step_name}")
        subprocess.run(command, check=True, cwd=ROOT)

    print("result=completed")
    print("source=unified_lexicon_source_database")
    if args.skip_runtime_apply:
        print("runtime_refresh=skipped")
    else:
        print("runtime_refresh=applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
