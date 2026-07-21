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
    iter_clean_targets,
    lint_runtime_db_file,
    lint_runtime_json_file,
    lint_source_db_file,
    make_report,
)

DEFAULT_RUNTIME_DB = ROOT / "yime" / "pinyin_hanzi.db"


def resolve_runtime_json_path(raw: str) -> Path | None:
    if raw.strip():
        path = Path(raw)
        return path if path.exists() else None
    for path in (
        generated_runtime_candidates_json_path(ROOT),
        resolve_runtime_candidates_json_path(ROOT / "yime"),
    ):
        if path.exists():
            return path
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
        help="将变更写回词库（尚未启用，当前会报错退出）",
    )
    parser.add_argument(
        "--output",
        default=str(ROOT / ".generated" / "lexicon_clean_plan.json"),
        help="dry-run 计划输出路径",
    )
    return parser.parse_args()


def build_plan(report: dict[str, object]) -> dict[str, object]:
    targets = list(iter_clean_targets(report))
    return {
        "tool": "lexicon_clean",
        "mode": "dry-run",
        "apply_enabled": False,
        "summary": {
            "planned_action_count": len(targets),
            **report["summary"],
        },
        "planned_actions": targets,
        "notes": [
            "当前不会修改词库。确认规则与白名单后，再在后续版本启用 --apply。",
            "发版前请优先使用 tools/lexicon_lint.py 审阅完整报告。",
        ],
    }


def main() -> int:
    args = parse_args()

    if args.apply:
        print(
            "lexicon_clean --apply 尚未启用。请先运行 tools/lexicon_lint.py 审阅报告，"
            "并在 docs/LEXICON_LINT.md 中记录的流程下人工确认。",
            file=sys.stderr,
        )
        return 2

    inputs: dict[str, str] = {}
    report = make_report(sample_limit=args.sample_limit, inputs=inputs)

    runtime_json = resolve_runtime_json_path(args.runtime_json)
    runtime_db = resolve_runtime_db_path(args.runtime_db)
    source_db = resolve_source_db_path(args.source_db)

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

    print(f"mode: dry-run (no files modified)")
    print(f"plan: {output_path}")
    print(f"planned_action_count: {plan['summary']['planned_action_count']}")
    print(f"errors: {plan['summary']['error_count']}")
    print(f"warnings: {plan['summary']['warning_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
