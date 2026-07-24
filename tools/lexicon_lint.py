from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from yime.asset_paths import (  # noqa: E402
    generated_runtime_candidates_json_path,
    resolve_runtime_candidates_json_path,
    resolve_lexicon_source_db_path,
)
from yime.utils.lexicon_quality import (  # noqa: E402
    finalize_report,
    lint_runtime_db_file,
    lint_runtime_json_file,
    lint_source_db_file,
    make_report,
)

DEFAULT_RUNTIME_DB = ROOT / "yime" / "pinyin_hanzi.db"
DEFAULT_OUTPUT = ROOT / ".generated" / "lexicon_lint_report.json"


def configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "系统词库质检（只读）。"
            "默认不修改任何词库文件；输出 JSON 报告供发版前审阅。"
        ),
    )
    parser.add_argument(
        "--runtime-json",
        default="",
        help=(
            "runtime_candidates_by_code_true.json 路径；"
            "默认优先 .generated/，否则 yime/reports/ 下的副本。"
        ),
    )
    parser.add_argument(
        "--runtime-db",
        default="",
        help="运行时 SQLite 路径（yime/pinyin_hanzi.db）。与 --runtime-json 可同时指定。",
    )
    parser.add_argument(
        "--source-db",
        default="",
        help="统一源词库 SQLite 路径（source_lexicon.sqlite3）。可选，用于源层短语规则扫描。",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="JSON 报告输出路径，默认 .generated/lexicon_lint_report.json",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=20,
        help="每个问题类别最多保留多少条样例",
    )
    parser.add_argument(
        "--fail-on-warnings",
        action="store_true",
        help="存在 warning 时也返回非零退出码（默认仅 errors 导致失败）",
    )
    return parser.parse_args()


def resolve_runtime_json_path(raw: str) -> Path | None:
    if raw.strip():
        path = Path(raw)
        return path if path.exists() else None
    return None


def resolve_runtime_db_path(raw: str) -> Path | None:
    if raw.strip():
        path = Path(raw)
        return path if path.exists() else None
    if DEFAULT_RUNTIME_DB.exists():
        return DEFAULT_RUNTIME_DB
    return None


def resolve_source_db_path(raw: str) -> Path | None:
    if raw.strip():
        path = Path(raw)
        return path if path.exists() else None
    path = resolve_lexicon_source_db_path(ROOT)
    return path if path.exists() else None


def print_summary(report: dict[str, object]) -> None:
    summary = report["summary"]
    print(f"candidate_rows: {summary['candidate_rows']}")
    print(f"source_phrase_rows: {summary['source_phrase_rows']}")
    print(f"errors: {summary['error_count']}")
    print(f"warnings: {summary['warning_count']}")
    print(f"suffix_particle_count: {summary['suffix_particle_count']}")
    print(f"source_suffix_particle_count: {summary['source_suffix_particle_count']}")
    print(f"placeholder_phrase_count: {summary['placeholder_phrase_count']}")


def main() -> int:
    configure_utf8_stdio()
    args = parse_args()
    if args.sample_limit < 0:
        print("--sample-limit 不能小于 0", file=sys.stderr)
        return 2

    explicit_paths = {
        "--runtime-json": args.runtime_json,
        "--runtime-db": args.runtime_db,
        "--source-db": args.source_db,
    }
    missing_explicit = [
        f"{flag}={raw}"
        for flag, raw in explicit_paths.items()
        if raw.strip() and not Path(raw).exists()
    ]
    if missing_explicit:
        print("显式指定的输入不存在：", file=sys.stderr)
        for item in missing_explicit:
            print(f"  {item}", file=sys.stderr)
        return 2

    inputs: dict[str, str] = {}
    report = make_report(sample_limit=args.sample_limit, inputs=inputs)

    has_explicit_input = any(raw.strip() for raw in explicit_paths.values())
    if has_explicit_input:
        runtime_json = resolve_runtime_json_path(args.runtime_json)
        runtime_db = (
            resolve_runtime_db_path(args.runtime_db)
            if args.runtime_db.strip()
            else None
        )
        source_db = (
            resolve_source_db_path(args.source_db)
            if args.source_db.strip()
            else None
        )
    else:
        # 默认只选择一个权威输入，避免同一批候选从 JSON、运行库和来源库重复计数。
        runtime_json = None
        runtime_db = resolve_runtime_db_path("")
        source_db = None
        if runtime_db is None:
            for candidate in (
                generated_runtime_candidates_json_path(ROOT),
                resolve_runtime_candidates_json_path(ROOT / "yime"),
            ):
                if candidate.exists():
                    runtime_json = candidate
                    break
        if runtime_db is None and runtime_json is None:
            source_db = resolve_source_db_path("")

    if runtime_json is not None:
        inputs["runtime_json"] = str(runtime_json)
        lint_runtime_json_file(runtime_json, report)
    if runtime_db is not None:
        inputs["runtime_db"] = str(runtime_db)
        lint_runtime_db_file(runtime_db, report)
    if source_db is not None:
        inputs["source_db"] = str(source_db)
        lint_source_db_file(source_db, report)

    if not inputs:
        print(
            "未找到可扫描的输入文件。请先导出 runtime JSON 或指定路径：",
            file=sys.stderr,
        )
        print(
            "  python tools/lexicon_lint.py --runtime-json .generated/runtime_candidates_by_code_true.json",
            file=sys.stderr,
        )
        return 2

    finalized = finalize_report(report)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(finalized, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"report: {output_path}")
    print_summary(finalized)

    if finalized["summary"]["error_count"]:
        return 1
    if args.fail_on_warnings and finalized["summary"]["warning_count"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
