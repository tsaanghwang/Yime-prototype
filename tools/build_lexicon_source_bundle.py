#!/usr/bin/env python3
"""Build the gated Unihan/pypinyin/Wanxiang/BCC source lexicon bundle."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from yime.lexicon_bundle.builder import BundleInputs, build_bundle, default_inputs


def parse_args() -> argparse.Namespace:
    defaults = default_inputs()
    parser = argparse.ArgumentParser(
        description="Build a traceable, decoder-ready source lexicon bundle.",
    )
    parser.add_argument("--unihan", type=Path, default=defaults.unihan)
    parser.add_argument("--pypinyin-phrases", type=Path, default=defaults.pypinyin_phrases)
    parser.add_argument("--bcc-words", type=Path, default=defaults.bcc_words)
    parser.add_argument("--bcc-chars", type=Path, default=defaults.bcc_chars)
    parser.add_argument("--decoder-inventory", type=Path, default=defaults.decoder_inventory)
    parser.add_argument(
        "--wanxiang-root",
        type=Path,
        default=ROOT.parent / "RIME-LMDG",
        help="Local RIME-LMDG checkout; dicts/cuoyin and dicts/mixed are excluded.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / ".generated" / "lexicon_source_bundle",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    wanxiang_defaults = default_inputs(args.wanxiang_root)
    inputs = BundleInputs(
        unihan=args.unihan.resolve(),
        pypinyin_phrases=args.pypinyin_phrases.resolve(),
        bcc_words=args.bcc_words.resolve(),
        bcc_chars=args.bcc_chars.resolve(),
        wanxiang_files=wanxiang_defaults.wanxiang_files,
        decoder_inventory=args.decoder_inventory.resolve(),
    )
    result = build_bundle(inputs, args.output_dir.resolve())
    payload = json.loads(result.manifest.read_text(encoding="utf-8"))
    print(json.dumps(payload["counts"], ensure_ascii=False, indent=2))
    print(f"bundle: {result.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
