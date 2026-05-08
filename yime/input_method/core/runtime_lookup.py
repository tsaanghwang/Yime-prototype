from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class RuntimeLookupPlan:
    """Resolved runtime lookup target for the current input buffer."""

    lookup_code: str
    active_code: str
    syllable_count: int
    trailing_code_count: int
    truncated_to_recent: bool
    phrase_mode: bool


def split_complete_syllables(canonical: str) -> List[str]:
    complete_length = (len(canonical) // 4) * 4
    return [canonical[index:index + 4] for index in range(0, complete_length, 4)]


def build_runtime_lookup_plan(canonical: str) -> RuntimeLookupPlan:
    syllables = split_complete_syllables(canonical)
    trailing_code_count = len(canonical) % 4
    if not syllables:
        return RuntimeLookupPlan(
            lookup_code="",
            active_code=canonical,
            syllable_count=0,
            trailing_code_count=trailing_code_count,
            truncated_to_recent=False,
            phrase_mode=False,
        )

    recent_syllables = syllables[-4:]
    truncated_to_recent = len(syllables) > len(recent_syllables)
    phrase_mode = trailing_code_count == 0 and len(recent_syllables) >= 2
    if phrase_mode:
        return RuntimeLookupPlan(
            lookup_code="".join(recent_syllables),
            active_code="".join(recent_syllables),
            syllable_count=len(recent_syllables),
            trailing_code_count=0,
            truncated_to_recent=truncated_to_recent,
            phrase_mode=True,
        )

    return RuntimeLookupPlan(
        lookup_code=recent_syllables[-1],
        active_code=recent_syllables[-1],
        syllable_count=1,
        trailing_code_count=trailing_code_count,
        truncated_to_recent=truncated_to_recent,
        phrase_mode=False,
    )


def build_runtime_mode_hint(canonical: str, plan: RuntimeLookupPlan) -> str:
    if plan.trailing_code_count and canonical:
        completed = len(split_complete_syllables(canonical))
        if completed:
            return (
                f"已完成 {completed} 个音节，当前第 {completed + 1} 个音节"
                f"输入到 {plan.trailing_code_count}/4 码。"
            )
        return f"当前 {plan.trailing_code_count}/4 码，继续输入。"

    if plan.phrase_mode:
        if plan.truncated_to_recent:
            return f"已自动截取最近 {plan.syllable_count} 个完整音节进行词语查找。"
        return f"按 {plan.syllable_count} 个完整音节进行词语查找。"

    if len(canonical) > 4:
        return f"已自动截取最近 4 码，总输入 {len(canonical)} 码。"

    return ""


def should_expand_phrase_prefix(plan: RuntimeLookupPlan) -> bool:
    return (
        plan.trailing_code_count == 0
        and not plan.phrase_mode
        and plan.syllable_count == 1
        and len(plan.lookup_code) == 4
    )


def build_phrase_tree_lookup(canonical: str, plan: RuntimeLookupPlan) -> str:
    normalized_canonical = str(canonical or "").strip()
    if not normalized_canonical:
        return ""
    if len(normalized_canonical) < 4:
        return normalized_canonical
    if should_expand_phrase_prefix(plan):
        return plan.lookup_code
    if plan.trailing_code_count <= 0:
        return ""

    completed_syllables = split_complete_syllables(normalized_canonical)
    trailing_prefix = normalized_canonical[len(completed_syllables) * 4 :]
    if not trailing_prefix:
        return ""
    return "".join(completed_syllables[-3:]) + trailing_prefix
