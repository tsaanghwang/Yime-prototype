"""变长音元模型子包：承载变长切分与相邻相同音元合并。"""

from .loose_split import from_legacy_pinyin_chars, split_loose_encoded_string
from .simplification import (
    merge_adjacent_duplicate_symbols,
    simplify_ganyin_repeats,
    simplify_loose_structure,
)
from .transform import (
    VariableLengthYinyuanResult,
    merge_adjacent_equal_yinyuan,
    to_variable_length_yinyuan_code,
    transform_full_code,
    transform_yinjie,
)

__all__ = [
    "VariableLengthYinyuanResult",
    "from_legacy_pinyin_chars",
    "merge_adjacent_equal_yinyuan",
    "merge_adjacent_duplicate_symbols",
    "simplify_ganyin_repeats",
    "simplify_loose_structure",
    "split_loose_encoded_string",
    "to_variable_length_yinyuan_code",
    "transform_full_code",
    "transform_yinjie",
]
