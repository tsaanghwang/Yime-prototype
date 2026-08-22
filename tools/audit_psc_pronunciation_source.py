#!/usr/bin/env python3
"""Audit the canonical source lexicon against the local PSC evidence database."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from yime.lexicon_bundle.psc_audit import run_audit


def default_psc_database() -> Path:
    configured = os.environ.get("PSC_OUTLINE_DB")
    if configured:
        return Path(configured)
    return ROOT / "external_data" / "psc_outline" / "psc_outline_ocr.sqlite3"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "以只读方式比较 PSC 2021/2024 对照库与原型规范读音真源，"
            "生成独立审计库和人工复核队列。"
        )
    )
    parser.add_argument(
        "--source-db",
        type=Path,
        default=ROOT / ".generated" / "lexicon_source_bundle" / "source_lexicon.sqlite3",
        help="原型统一规范读音真源；始终以 SQLite 只读模式打开。",
    )
    parser.add_argument(
        "--psc-db",
        type=Path,
        default=default_psc_database(),
        help="仓库内 PSC 对照数据库；可用 PSC_OUTLINE_DB 覆盖默认路径。",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / ".generated" / "psc_pronunciation_audit",
        help="独立审计产物目录。",
    )
    args = parser.parse_args()

    artifacts = run_audit(args.source_db, args.psc_db, args.output_dir)
    result = {
        "database": str(artifacts.database),
        "summary_json": str(artifacts.summary_json),
        "report_markdown": str(artifacts.report_markdown),
        "review_tsv": str(artifacts.review_tsv),
        "observations": artifacts.observation_count,
        "needs_review_observations": artifacts.review_observation_count,
        "review_cases": artifacts.review_case_count,
        "pending_review_cases": artifacts.pending_case_count,
        "decided_review_cases": artifacts.decided_case_count,
        "source_lexicon_modified": False,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
