#!/usr/bin/env python3
"""Export replay-gated compact component lexicons for Windows Yime."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from yime.input_model.core_trial_export import export_core_trial_lexicons


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Export fixed-code Rime dictionaries from the static-capacity "
            "proposal without modifying the production runtime lexicon."
        )
    )
    parser.add_argument(
        "--source-database",
        type=Path,
        default=(
            ROOT
            / ".generated"
            / "lexicon_source_bundle"
            / "source_lexicon.sqlite3"
        ),
    )
    parser.add_argument(
        "--capacity-database",
        type=Path,
        default=(
            ROOT
            / ".generated"
            / "static_lexicon_capacity"
            / "static_capacity.sqlite3"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / ".generated" / "core_trial_lexicons",
    )
    parser.add_argument(
        "--capacity",
        action="append",
        type=int,
        help=(
            "Distinct-text capacity to export; repeat for multiple tiers. "
            "Default: mandatory, +10k, +50k, recommended, +100k, +150k."
        ),
    )
    parser.add_argument(
        "--include-pinyin-source",
        action="append",
        default=[],
        help=(
            "Include every gated text carrying this exact pinyin source, "
            "in addition to the selected capacity tier; repeat as needed."
        ),
    )
    parser.add_argument(
        "--include-source-lengths",
        action="append",
        default=[],
        metavar="SOURCE:LENGTHS",
        help=(
            "Include gated texts from one source only at comma-separated "
            "lengths, for example pypinyin:2,3,4; repeat as needed."
        ),
    )
    parser.add_argument(
        "--trial-label",
        default="",
        help="Stable label used in generated trial directory and dictionary names.",
    )
    parser.add_argument(
        "--include-wanxiang-category-lengths",
        action="append",
        default=[],
        metavar="CATEGORY:LENGTHS",
        help=(
            "Include gated Wanxiang texts from one category only at "
            "comma-separated lengths; repeat as needed."
        ),
    )
    return parser.parse_args()


def parse_source_lengths(values: list[str]) -> dict[str, tuple[int, ...]]:
    result: dict[str, set[int]] = {}
    for value in values:
        source, separator, lengths_text = value.partition(":")
        if not separator or not source.strip() or not lengths_text.strip():
            raise ValueError(
                f"Invalid --include-source-lengths value: {value!r}"
            )
        try:
            lengths = {
                int(item.strip())
                for item in lengths_text.split(",")
                if item.strip()
            }
        except ValueError as exc:
            raise ValueError(
                f"Invalid text length in --include-source-lengths: {value!r}"
            ) from exc
        if not lengths:
            raise ValueError(
                f"No text lengths in --include-source-lengths: {value!r}"
            )
        result.setdefault(source.strip(), set()).update(lengths)
    return {
        source: tuple(sorted(lengths))
        for source, lengths in sorted(result.items())
    }


def main() -> int:
    args = parse_args()
    result = export_core_trial_lexicons(
        source_database=args.source_database,
        capacity_database=args.capacity_database,
        output_dir=args.output_dir,
        capacities=args.capacity,
        include_pinyin_sources=args.include_pinyin_source,
        include_source_lengths=parse_source_lengths(
            args.include_source_lengths
        ),
        include_wanxiang_category_lengths=parse_source_lengths(
            args.include_wanxiang_category_lengths
        ),
        trial_label=args.trial_label,
        repo_root=ROOT,
    )
    print(f"mandatory_capacity: {result.mandatory_capacity}")
    print(f"recommended_capacity: {result.recommended_capacity}")
    for tier in result.tiers:
        print(
            f"capacity={tier.capacity} texts={tier.selected_texts} "
            f"readings={tier.reading_entries} "
            f"dictionary={tier.dictionary_path}"
        )
    print(f"manifest: {result.index_manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
