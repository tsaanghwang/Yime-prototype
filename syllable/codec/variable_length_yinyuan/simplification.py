"""变长音元模型的兼容化简入口。"""

from __future__ import annotations

from typing import Iterable

from syllable.codec.model_full_code import Yinjie
from syllable.codec.variable_length_yinyuan.loose_split import split_loose_encoded_string
from syllable.codec.variable_length_yinyuan.transform import (
    merge_adjacent_equal_yinyuan,
    to_variable_length_yinyuan_code,
)


def merge_adjacent_duplicate_symbols(symbols: Iterable[str]) -> tuple[list[str], int]:
    """兼容旧名：合并相邻且完全相同的音元。"""
    return merge_adjacent_equal_yinyuan(symbols)


def simplify_ganyin_repeats(
    full_code: str | list[str] | tuple[str, ...] | None,
    *,
    virtual_initial: str | None = None,
) -> str:
    """兼容旧名：将四元模型转换为变长音元码。

    新代码应优先使用 ``to_variable_length_yinyuan_code``。旧名保留是为了
    兼容现有调用面。
    """
    if full_code is None:
        return ""
    if not full_code:
        return ""
    return to_variable_length_yinyuan_code(full_code, virtual_initial=virtual_initial)


def simplify_loose_structure(yinjie: Yinjie, *, virtual_initial: str | None = None) -> Yinjie:
    """全码化简后再按宽松规则切回 ``Yinjie``（变长音元视图，非四码 canonical）。"""
    simplified = simplify_ganyin_repeats(yinjie.to_code(), virtual_initial=virtual_initial)
    return split_loose_encoded_string(simplified)


__all__ = [
    "merge_adjacent_duplicate_symbols",
    "simplify_ganyin_repeats",
    "simplify_loose_structure",
]
