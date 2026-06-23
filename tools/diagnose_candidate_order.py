from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, cast

from yime.input_method.core import decoders as decoder_module
from yime.input_method.core.decoders import SQLiteRuntimeCandidateDecoder
from yime.input_method.utils.user_lexicon import resolve_canonical_code_from_numeric_pinyin


ROOT = Path(__file__).resolve().parent.parent
APP_DIR = ROOT / "yime"
USER_DB_PATH = APP_DIR / "user_lexicon.db"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="诊断某个编码下的候选排序和用户频率。")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--numeric-pinyin", help="按数字标调拼音诊断，例如：ri4 ben3")
    group.add_argument("--canonical-code", help="按规范化 4 码/多音节码诊断。")
    parser.add_argument("--limit", type=int, default=20, help="最多显示多少条结果。")
    return parser.parse_args()


def resolve_lookup_code(args: argparse.Namespace, decoder: SQLiteRuntimeCandidateDecoder) -> str:
    if args.canonical_code:
        return args.canonical_code.strip()
    canonical = resolve_canonical_code_from_numeric_pinyin(
        decoder.pinyin_to_canonical,
        args.numeric_pinyin or "",
    )
    if not canonical:
        raise SystemExit("无法根据 numeric-pinyin 解析出 canonical-code。")
    return canonical


def main() -> None:
    args = parse_args()
    decoder = SQLiteRuntimeCandidateDecoder(APP_DIR, user_db_path=USER_DB_PATH)
    lookup_code = resolve_lookup_code(args, decoder)
    decoder_any = cast(Any, decoder)
    raw_candidates = decoder_any.by_code.get(lookup_code, [])
    records = cast(Any, decoder)._payload_to_runtime_candidates(lookup_code, raw_candidates)
    ranked = cast(Any, decoder)._rank_runtime_candidates(records)

    print(f"user_lexicon_db={USER_DB_PATH}")
    print(f"lookup_code={lookup_code}")
    print(f"candidate_pool={len(records)}")
    print(f"ranked_candidate_entries={len(ranked)}")

    if not ranked:
        print("无结果")
        return

    for index, candidate in enumerate(ranked[: args.limit], start=1):
        user_freq_by_candidate = cast(Any, getattr(decoder, "_user_freq_by_candidate", {}))
        user_freq = user_freq_by_candidate.get(
            (candidate.lookup_code, candidate.text),
            0,
        )
        runtime_sort_key_fn = cast(Any, getattr(decoder_module, "_runtime_candidate_sort_key", None))
        sort_key = (
            cast(Any, runtime_sort_key_fn(candidate, user_freq))
            if callable(runtime_sort_key_fn)
            else "<unavailable>"
        )
        print(
            f"#{index} candidate_text={candidate.text} entry_type={candidate.entry_type} "
            f"pinyin={candidate.pinyin_tone} sort_weight={candidate.sort_weight} "
            f"persisted_reorder_frequency={user_freq} sort_key={sort_key}"
        )


if __name__ == "__main__":
    main()
