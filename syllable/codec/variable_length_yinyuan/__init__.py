"""变长音元模型子包：承载变长切分与相邻相同音元合并。"""

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
