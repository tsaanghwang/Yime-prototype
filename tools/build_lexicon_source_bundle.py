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
from yime.lexicon_bundle.character_tiers import CharacterTierSources


def parse_args() -> argparse.Namespace:
    defaults = default_inputs()
    parser = argparse.ArgumentParser(
        description="Build a traceable, decoder-ready source lexicon bundle.",
    )
    parser.add_argument("--unihan", type=Path, default=defaults.unihan)
    parser.add_argument("--pypinyin-phrases", type=Path, default=defaults.pypinyin_phrases)
    parser.add_argument("--decoder-inventory", type=Path, default=defaults.decoder_inventory)
    assert defaults.character_tier_sources is not None
    parser.add_argument(
        "--unihan-other-mappings",
        type=Path,
        default=defaults.character_tier_sources.other_mappings,
    )
    parser.add_argument(
        "--unihan-readings",
        type=Path,
        default=defaults.character_tier_sources.readings,
    )
    parser.add_argument(
        "--unihan-character-db",
        type=Path,
        default=defaults.character_tier_sources.character_catalog_db,
    )
    parser.add_argument(
        "--yinjie-codebook",
        type=Path,
        default=defaults.character_tier_sources.yinjie_codebook,
    )
    parser.add_argument(
        "--source-compliance-policy",
        type=Path,
        default=defaults.source_compliance_policy,
    )
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
        bcc_word_files=wanxiang_defaults.bcc_word_files,
        bcc_char_files=wanxiang_defaults.bcc_char_files,
        wanxiang_files=wanxiang_defaults.wanxiang_files,
        decoder_inventory=args.decoder_inventory.resolve(),
        source_compliance_policy=args.source_compliance_policy.resolve(),
        character_tier_sources=CharacterTierSources(
            other_mappings=args.unihan_other_mappings.resolve(),
            readings=args.unihan_readings.resolve(),
            character_catalog_db=args.unihan_character_db.resolve(),
            yinjie_codebook=args.yinjie_codebook.resolve(),
        ),
    )
    result = build_bundle(inputs, args.output_dir.resolve())
    payload = json.loads(result.manifest.read_text(encoding="utf-8"))
    print(json.dumps(payload["counts"], ensure_ascii=False, indent=2))
    print(f"bundle: {result.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
