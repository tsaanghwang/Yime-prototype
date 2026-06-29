"""变长音元模型的化简辅助。"""

from __future__ import annotations

from typing import Iterable

from syllable.codec.model_full_code import Yinjie
from syllable.codec.variable_length_yinyuan.loose_split import split_loose_encoded_string


def merge_adjacent_duplicate_symbols(symbols: Iterable[str]) -> tuple[list[str], int]:
    """合并相邻重复音元并返回合并后的序列及合并次数。"""
    merged: list[str] = []
    merged_repeat_count = 0
    for symbol in symbols:
        if not merged or merged[-1] != symbol:
            merged.append(symbol)
            continue
        merged_repeat_count += 1
    return merged, merged_repeat_count


def simplify_ganyin_repeats(full_code: str | list[str] | tuple[str, ...] | None) -> str:
    """将模型全码按音值等价规则化简（当前仅合并干音内部相邻重复音元）。"""
    if full_code is None:
        return ""

    if isinstance(full_code, (list, tuple)):
        seq = [str(x) for x in full_code]
    else:
        seq = list(str(full_code))

    if not seq:
        return ""

    if len(seq) == 4:
        head = seq[0]
        ganyin_seq = seq[1:4]
        has_head = True
    elif len(seq) == 3:
        head = None
        ganyin_seq = seq[0:3]
        has_head = False
    else:
        head = seq[0] if len(seq) > 1 else None
        ganyin_seq = seq[1:] if len(seq) > 1 else []
        has_head = head is not None

    simple_ganyin, _ = merge_adjacent_duplicate_symbols(ganyin_seq)

    parts: list[str] = []
    if has_head and head is not None:
        parts.append(str(head))
    parts.extend(str(x) for x in simple_ganyin)
    return "".join(parts)


def simplify_loose_structure(yinjie: Yinjie) -> Yinjie:
    """全码化简后再按宽松规则切回 ``Yinjie``（变长音元视图，非四码 canonical）。"""
    simplified = simplify_ganyin_repeats(yinjie.to_code())
    return split_loose_encoded_string(simplified)


__all__ = [
    "merge_adjacent_duplicate_symbols",
    "simplify_ganyin_repeats",
    "simplify_loose_structure",
]
