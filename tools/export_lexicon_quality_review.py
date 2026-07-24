#!/usr/bin/env python3
"""Export a ranked, read-only review queue for lexicon-quality signals."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from yime.utils.lexicon_review import export_review_queue  # noqa: E402


DEFAULT_RUNTIME_DB = ROOT / "yime" / "pinyin_hanzi.db"
DEFAULT_INPUT_MODEL = (
    ROOT / ".generated" / "input_candidate_model" / "input_model.sqlite3"
)
DEFAULT_OUTPUT = ROOT / ".generated" / "lexicon_quality_review"


def configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "把词库尾助词质检信号与 input_model 覆盖层合并成只读审阅队列；"
            "不会写 assessments 或生产词库。"
        ),
    )
    parser.add_argument("--runtime-db", type=Path, default=DEFAULT_RUNTIME_DB)
    parser.add_argument("--input-model", type=Path, default=DEFAULT_INPUT_MODEL)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary-limit", type=int, default=100)
    parser.add_argument("--per-suffix-limit", type=int, default=10)
    return parser.parse_args()


def main() -> int:
    configure_utf8_stdio()
    args = parse_args()
    try:
        result = export_review_queue(
            runtime_database=args.runtime_db,
            input_model_database=args.input_model,
            output_directory=args.output_dir,
            summary_limit=args.summary_limit,
            per_suffix_limit=args.per_suffix_limit,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f"queue: {result.queue_path}")
    print(f"summary: {result.summary_path}")
    print(f"manifest: {result.manifest_path}")
    print(f"queue_count: {result.queue_count}")
    print(f"excluded_decided_count: {result.excluded_decided_count}")
    print(f"tier_counts: {result.tier_counts}")
    print(f"suffix_counts: {result.suffix_counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
