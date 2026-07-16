"""四元模型到变长音元模型的转换。

转换规则只有两条，且顺序固定：

1. 先合并相邻且完全相同的音元；
2. 再省略虚首音。

这里依赖四元模型的不变量：首音元与首音后的任一干音音元不会相同。
因此先合并再省略虚首音，不会隐藏跨边界重复。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from syllable.codec.model_full_code import Yinjie


FOUR_YINYUAN_CODE_LENGTH = 4


@dataclass(frozen=True)
class VariableLengthYinyuanResult:
    """四元模型转换为变长音元模型后的结果。"""

    full_code: str
    merged_code: str
    variable_code: str
    virtual_initial: str | None
    omitted_virtual_initial: bool
    merged_adjacent_count: int


def merge_adjacent_equal_yinyuan(symbols: Iterable[str]) -> tuple[list[str], int]:
    """合并相邻且完全相同的音元。"""
    merged: list[str] = []
    merged_adjacent_count = 0
    for symbol in symbols:
        if not merged or merged[-1] != symbol:
            merged.append(symbol)
            continue
        merged_adjacent_count += 1
    return merged, merged_adjacent_count


def _normalize_full_code(full_code: str | Sequence[str]) -> str:
    if isinstance(full_code, str):
        normalized = full_code
    else:
        normalized = "".join(str(symbol) for symbol in full_code)

    if len(normalized) != FOUR_YINYUAN_CODE_LENGTH:
        raise ValueError(
            f"full_code must be a four-yinyuan code, got length {len(normalized)}: {normalized!r}"
        )
    return normalized


def transform_full_code(
    full_code: str | Sequence[str],
    *,
    virtual_initial: str | None = None,
) -> VariableLengthYinyuanResult:
    """把等长四元码转换为变长音元码。"""
    normalized_code = _normalize_full_code(full_code)
    merged_symbols, merged_adjacent_count = merge_adjacent_equal_yinyuan(normalized_code)
    merged_code = "".join(merged_symbols)

    omitted_virtual_initial = bool(
        virtual_initial and merged_symbols and merged_symbols[0] == virtual_initial
    )
    if omitted_virtual_initial:
        variable_symbols = merged_symbols[1:]
    else:
        variable_symbols = merged_symbols

    return VariableLengthYinyuanResult(
        full_code=normalized_code,
        merged_code=merged_code,
        variable_code="".join(variable_symbols),
        virtual_initial=virtual_initial,
        omitted_virtual_initial=omitted_virtual_initial,
        merged_adjacent_count=merged_adjacent_count,
    )


def transform_yinjie(
    yinjie: Yinjie,
    *,
    virtual_initial: str | None = None,
) -> VariableLengthYinyuanResult:
    """把 ``Yinjie`` 四元模型对象转换为变长音元模型。"""
    return transform_full_code(yinjie.to_code(), virtual_initial=virtual_initial)


def to_variable_length_yinyuan_code(
    full_code: str | Sequence[str],
    *,
    virtual_initial: str | None = None,
) -> str:
    """返回四元码对应的变长音元码字符串。"""
    return transform_full_code(full_code, virtual_initial=virtual_initial).variable_code


__all__ = [
    "FOUR_YINYUAN_CODE_LENGTH",
    "VariableLengthYinyuanResult",
    "merge_adjacent_equal_yinyuan",
    "to_variable_length_yinyuan_code",
    "transform_full_code",
    "transform_yinjie",
]
