"""变长音元模型兼容子包。

推荐新代码从 ``syllable.codec.variable_length_yinyuan`` import；本包名保留
为历史兼容路径。
"""

from .loose_split import from_legacy_pinyin_chars, split_loose_encoded_string
from .simplification import (
    merge_adjacent_duplicate_symbols,
    simplify_ganyin_repeats,
    simplify_loose_structure,
)

__all__ = [
    "from_legacy_pinyin_chars",
    "merge_adjacent_duplicate_symbols",
    "simplify_ganyin_repeats",
    "simplify_loose_structure",
    "split_loose_encoded_string",
]
