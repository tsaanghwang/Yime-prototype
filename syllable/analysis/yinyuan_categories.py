"""共享的片音 / 音元类别轴。

本模块只表达跨层共享的“噪音 / 乐音”类别，不承载片音到音元的归并规则，
也不承载结构段（首音 / 干音 / 呼音 / 主音 / 末音）信息。
"""

from __future__ import annotations

from enum import Enum


class YinyuanCategory(str, Enum):
    """片音层与音元层共享的类别轴。"""

    ZAOYIN = "zaoyin"
    YUEYIN = "yueyin"


def infer_category_from_pitch(pitch: object) -> YinyuanCategory:
    """按当前仓库约定从音高表现推断共享类别。"""
    if pitch is None or isinstance(pitch, bool):
        return YinyuanCategory.ZAOYIN
    return YinyuanCategory.YUEYIN
