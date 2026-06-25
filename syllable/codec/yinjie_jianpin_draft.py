"""音值简码化简的兼容入口。"""

from __future__ import annotations

try:
    from .model_full_code import Yinjie
    from .phonological_code import simplify_ganyin_repeats, simplify_loose_structure
except ImportError:
    from model_full_code import Yinjie
    from phonological_code import simplify_ganyin_repeats, simplify_loose_structure

__all__ = ["Yinjie", "simplify_ganyin_repeats", "simplify_loose_structure"]
