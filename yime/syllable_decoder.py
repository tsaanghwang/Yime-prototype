"""Legacy shim for the old syllable decoder helpers.

The real compatibility implementation now lives next to the retained
legacy pinyin reference-table rebuild chain.
"""

from typing import Any

from yime.utils.legacy_pinyin_tables import syllable_decoder as _legacy_impl

SyllableDecoder = _legacy_impl.SyllableDecoder
_normalize_split: Any = getattr(_legacy_impl, "_normalize_split")
is_pua_string = _legacy_impl.is_pua_string
is_valid_encoded_string = _legacy_impl.is_valid_encoded_string
main = _legacy_impl.main

__all__ = [
    "SyllableDecoder",
    "_normalize_split",
    "is_pua_string",
    "is_valid_encoded_string",
    "main",
]


if __name__ == "__main__":
    main()
