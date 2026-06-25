"""音值简码宽松切分的兼容入口。"""

from __future__ import annotations

try:
    from .phonological_code import from_legacy_pinyin_chars, split_loose_encoded_string
except ImportError:
    from phonological_code import from_legacy_pinyin_chars, split_loose_encoded_string

__all__ = ["from_legacy_pinyin_chars", "split_loose_encoded_string"]
