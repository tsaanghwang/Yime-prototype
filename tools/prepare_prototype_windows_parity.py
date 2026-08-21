#!/usr/bin/env python3
"""Prepare the compact prototype database used for Windows-parity evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from yime.utils.prototype_runtime_parity import build_compact_parity_database
from yime.utils.rime_export import layout_projection_digest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-database",
        type=Path,
        default=ROOT / ".generated/two_level_runtime_trial/runtime/pinyin_hanzi.db",
    )
    parser.add_argument(
        "--dictionary-manifest",
        type=Path,
        default=ROOT / ".generated/two_level_runtime_trial/dictionary.manifest.json",
    )
    parser.add_argument(
        "--runtime-manifest",
        type=Path,
        default=ROOT / ".generated/two_level_runtime_trial/runtime.manifest.json",
    )
    parser.add_argument(
        "--output-database",
        type=Path,
        default=ROOT / ".generated/prototype_windows_parity/pinyin_hanzi.db",
    )
    parser.add_argument(
        "--output-manifest",
        type=Path,
        default=(
            ROOT
            / ".generated/prototype_windows_parity/prototype_runtime_manifest.json"
        ),
    )
    args = parser.parse_args()
    payload = build_compact_parity_database(
        source_database=args.source_database.resolve(),
        output_database=args.output_database.resolve(),
        dictionary_manifest_path=args.dictionary_manifest.resolve(),
        runtime_manifest_path=args.runtime_manifest.resolve(),
        layout_digest=layout_projection_digest(ROOT),
        output_manifest_path=args.output_manifest.resolve(),
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
