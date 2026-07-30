"""UI模块：候选框、编辑框、样式"""

from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from .candidate_box import CandidateBox

__all__ = ["CandidateBox"]


def __getattr__(name: str) -> Any:
    if name != "CandidateBox":
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    from .candidate_box import CandidateBox

    globals()[name] = CandidateBox
    return CandidateBox
