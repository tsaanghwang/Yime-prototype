"""音值简码子包：承载音值等价的变长化简。"""

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
