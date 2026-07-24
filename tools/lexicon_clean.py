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
    iter_review_samples,
    lint_runtime_db_file,
    lint_runtime_json_file,
    lint_source_db_file,
    make_report,
)

DEFAULT_RUNTIME_DB = ROOT / "yime" / "pinyin_hanzi.db"


def configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")


def resolve_runtime_json_path(raw: str) -> Path | None:
    if raw.strip():
        path = Path(raw)
        return path if path.exists() else None
    return None


def resolve_runtime_db_path(raw: str) -> Path | None:
    if raw.strip():
        path = Path(raw)
        return path if path.exists() else None
    return DEFAULT_RUNTIME_DB if DEFAULT_RUNTIME_DB.exists() else None


def resolve_source_db_path(raw: str) -> Path | None:
    if raw.strip():
        path = Path(raw)
        return path if path.exists() else None
    path = resolve_lexicon_source_db_path(ROOT)
    return path if path.exists() else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "系统词库清洗占位工具。"
            "当前仅支持 dry-run：列出将来可能清理的词条，不写回任何数据库或 JSON。"
        ),
    )
    parser.add_argument(
        "--runtime-json",
        default="",
        help="与 lexicon_lint 相同",
    )
    parser.add_argument(
        "--runtime-db",
        default="",
        help="与 lexicon_lint 相同",
    )
    parser.add_argument(
        "--source-db",
        default="",
        help="与 lexicon_lint 相同",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=20,
        help="每个问题类别最多保留多少条样例",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="保留参数；写回生产词库被禁用，使用时会报错退出",
    )
    parser.add_argument(
        "--output",
        default=str(ROOT / ".generated" / "lexicon_clean_plan.json"),
        help="dry-run 计划输出路径",
    )
    return parser.parse_args()


def build_plan(report: dict[str, object]) -> dict[str, object]:
    review_samples = list(iter_review_samples(report))
    return {
        "tool": "lexicon_clean",
        "mode": "dry-run-review",
        "apply_enabled": False,
        "inputs": report["inputs"],
        "sample_limit": report["sample_limit"],
        "summary": {
            "review_sample_count": len(review_samples),
            **report["summary"],
        },
        "review_samples": review_samples,
        "notes": [
            "当前不会修改词库；review_samples 只是受 sample_limit 限制的人工审阅样例，不是全量清洗动作。",
            "发版前请优先使用 tools/lexicon_lint.py 审阅完整报告。",
        ],
    }


def main() -> int:
    configure_utf8_stdio()
    args = parse_args()

    if args.apply:
        print(
            "lexicon_clean --apply 已禁用。请先运行 tools/lexicon_lint.py 审阅报告，"
            "再把人工决定写入独立候选整理覆盖层。",
            file=sys.stderr,
        )
        return 2
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
        print("未找到可扫描的输入文件。请先运行 export 或显式传入路径。", file=sys.stderr)
        return 2

    finalized = finalize_report(report)
    plan = build_plan(finalized)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    print("mode: dry-run-review (no files modified)")
    print(f"plan: {output_path}")
    print(f"review_sample_count: {plan['summary']['review_sample_count']}")
    print(f"errors: {plan['summary']['error_count']}")
    print(f"warnings: {plan['summary']['warning_count']}")
    if plan["summary"]["error_count"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
