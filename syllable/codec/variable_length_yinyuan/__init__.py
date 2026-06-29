"""变长音元模型入口。

本包是 ``syllable.codec.phonological_code`` 的推荐命名入口；旧包名保留
为兼容路径。
"""

try:
    from ..phonological_code import (
        from_legacy_pinyin_chars,
        merge_adjacent_duplicate_symbols,
        simplify_ganyin_repeats,
        simplify_loose_structure,
        split_loose_encoded_string,
    )
except ImportError:
    from phonological_code import (
        from_legacy_pinyin_chars,
        merge_adjacent_duplicate_symbols,
        simplify_ganyin_repeats,
        simplify_loose_structure,
        split_loose_encoded_string,
    )

__all__ = [
    "from_legacy_pinyin_chars",
    "merge_adjacent_duplicate_symbols",
    "simplify_ganyin_repeats",
    "simplify_loose_structure",
    "split_loose_encoded_string",
]
