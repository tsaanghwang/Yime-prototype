from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import List


RECENT_SYLLABLE_PREFIX_CANDIDATE_LIMIT = 64
LONG_CONTEXT_PREFIX_1_CANDIDATE_LIMIT = 32
LONG_CONTEXT_PREFIX_2_CANDIDATE_LIMIT = 24
LONG_CONTEXT_PREFIX_3_CANDIDATE_LIMIT = 16


@dataclass(frozen=True)
class RuntimeLookupPlan:
    """Resolved runtime lookup target for the current input buffer."""

    stage: str
    phrase_prefix_pool: str
    phrase_prefix_limit: int
    lookup_code: str
    context_code: str
    active_code: str
    syllable_count: int
    trailing_code_count: int
    truncated_to_recent: bool
    phrase_mode: bool


@lru_cache(maxsize=None)
def _build_code_inventory_metadata(
    single_syllable_codes: frozenset[str],
) -> tuple[frozenset[str], int]:
    prefixes: set[str] = set()
    max_length = 0
    for code in single_syllable_codes:
        normalized_code = str(code or "").strip()
        if not normalized_code:
            continue
        max_length = max(max_length, len(normalized_code))
        for prefix_length in range(1, len(normalized_code) + 1):
            prefixes.add(normalized_code[:prefix_length])
    return frozenset(prefixes), max_length


def _split_complete_syllables_by_legacy_width(canonical: str) -> tuple[List[str], str]:
    complete_length = (len(canonical) // 4) * 4
    return (
        [canonical[index:index + 4] for index in range(0, complete_length, 4)],
        canonical[complete_length:],
    )


def _split_complete_syllables_by_inventory(
    canonical: str,
    single_syllable_codes: frozenset[str],
) -> tuple[List[str], str]:
    if not canonical or not single_syllable_codes:
        return _split_complete_syllables_by_legacy_width(canonical)

    prefixes, max_code_length = _build_code_inventory_metadata(single_syllable_codes)
    if max_code_length <= 0:
        return _split_complete_syllables_by_legacy_width(canonical)

    @lru_cache(maxsize=None)
    def resolve(start: int) -> tuple[str, tuple[str, ...]] | None:
        if start >= len(canonical):
            return "", ()

        best: tuple[int, int, int, tuple[str, ...], str] | None = None
        trailing = canonical[start:]
        trailing_is_prefix = trailing in prefixes
        best = (0, 1 if trailing_is_prefix else 0, 0, (), trailing)

        for end in range(min(len(canonical), start + max_code_length), start, -1):
            candidate = canonical[start:end]
            if candidate not in single_syllable_codes:
                continue
            suffix = resolve(end)
            if suffix is None:
                continue
            trailing_suffix, remaining_syllables = suffix
            completed_syllables = (candidate, *remaining_syllables)
            score = (
                len(canonical) - len(trailing_suffix),
                1 if not trailing_suffix else 0,
                len(completed_syllables),
                completed_syllables,
                trailing_suffix,
            )
            if best is None or score[:3] > best[:3]:
                best = score

        if best is None:
            return None
        return best[4], best[3]

    resolved = resolve(0)
    if resolved is None:
        return _split_complete_syllables_by_legacy_width(canonical)
    trailing_prefix, syllables = resolved
    return list(syllables), trailing_prefix


def split_complete_syllables(
    canonical: str,
    single_syllable_codes: frozenset[str] | None = None,
) -> List[str]:
    if single_syllable_codes:
        return _split_complete_syllables_by_inventory(canonical, single_syllable_codes)[0]
    return _split_complete_syllables_by_legacy_width(canonical)[0]


def resolve_long_context_prefix_pool(
    recent_syllables: List[str],
    trailing_prefix: str,
) -> tuple[str, str, int]:
    normalized_trailing_prefix = str(trailing_prefix or "").strip()
    if not normalized_trailing_prefix:
        return "", "", 0

    window_syllable_count = min(max(len(recent_syllables), 1), 3)
    if window_syllable_count == 1:
        return (
            "long-context-prefix-1",
            recent_syllables[-1] + normalized_trailing_prefix,
            LONG_CONTEXT_PREFIX_1_CANDIDATE_LIMIT,
        )
    if window_syllable_count == 2:
        return (
            "long-context-prefix-2",
            "".join(recent_syllables[-2:]) + normalized_trailing_prefix,
            LONG_CONTEXT_PREFIX_2_CANDIDATE_LIMIT,
        )
    return (
        "long-context-prefix-3",
        "".join(recent_syllables[-3:]) + normalized_trailing_prefix,
        LONG_CONTEXT_PREFIX_3_CANDIDATE_LIMIT,
    )


def build_runtime_lookup_plan(
    canonical: str,
    single_syllable_codes: frozenset[str] | None = None,
) -> RuntimeLookupPlan:
    if single_syllable_codes:
        syllables, trailing_prefix = _split_complete_syllables_by_inventory(
            canonical,
            single_syllable_codes,
        )
        trailing_code_count = len(trailing_prefix)
    else:
        syllables, trailing_prefix = _split_complete_syllables_by_legacy_width(canonical)
        trailing_code_count = len(trailing_prefix)
    if not syllables:
        return RuntimeLookupPlan(
            stage="A",
            phrase_prefix_pool="",
            phrase_prefix_limit=0,
            lookup_code="",
            context_code=canonical,
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
            stage="D",
            phrase_prefix_pool="",
            phrase_prefix_limit=0,
            lookup_code="".join(recent_syllables),
            context_code="".join(recent_syllables),
            active_code="".join(recent_syllables),
            syllable_count=len(recent_syllables),
            trailing_code_count=0,
            truncated_to_recent=truncated_to_recent,
            phrase_mode=True,
        )

    if trailing_code_count == 0:
        lookup_code = recent_syllables[-1]
        return RuntimeLookupPlan(
            stage="B",
            phrase_prefix_pool="recent-syllable-prefix",
            phrase_prefix_limit=RECENT_SYLLABLE_PREFIX_CANDIDATE_LIMIT,
            lookup_code=lookup_code,
            context_code=lookup_code,
            active_code=lookup_code,
            syllable_count=1,
            trailing_code_count=0,
            truncated_to_recent=truncated_to_recent,
            phrase_mode=False,
        )

    lookup_code = recent_syllables[-1]
    phrase_prefix_pool, context_code, phrase_prefix_limit = resolve_long_context_prefix_pool(
        recent_syllables,
        trailing_prefix,
    )

    return RuntimeLookupPlan(
        stage="C",
        phrase_prefix_pool=phrase_prefix_pool,
        phrase_prefix_limit=phrase_prefix_limit,
        lookup_code=lookup_code,
        context_code=context_code,
        active_code=lookup_code,
        syllable_count=len(recent_syllables),
        trailing_code_count=trailing_code_count,
        truncated_to_recent=truncated_to_recent,
        phrase_mode=False,
    )


def build_runtime_mode_hint(
    canonical: str,
    plan: RuntimeLookupPlan,
    single_syllable_codes: frozenset[str] | None = None,
) -> str:
    if plan.trailing_code_count and canonical:
        completed = len(split_complete_syllables(canonical, single_syllable_codes))
        if completed:
            if single_syllable_codes:
                return (
                    f"已完成 {completed} 个音节，当前第 {completed + 1} 个音节"
                    f"未完成，已输入 {plan.trailing_code_count} 码。"
                )
            return (
                f"已完成 {completed} 个音节，当前第 {completed + 1} 个音节"
                f"未完成，已输入 {plan.trailing_code_count} 码。"
            )
        if single_syllable_codes:
            return f"当前首音节未完成，已输入 {plan.trailing_code_count} 码。"
        return f"当前首音节未完成，已输入 {plan.trailing_code_count} 码。"

    if plan.phrase_mode:
        if plan.truncated_to_recent:
            return f"已自动截取最近 {plan.syllable_count} 个完整音节进行词语查找。"
        return f"按 {plan.syllable_count} 个完整音节进行词语查找。"

    if not single_syllable_codes and len(canonical) > 4:
        return f"已自动截取最近一个完整音节，总输入 {len(canonical)} 码。"

    return ""


def should_expand_phrase_prefix(plan: RuntimeLookupPlan) -> bool:
    return plan.stage == "B" and bool(plan.lookup_code)


def build_phrase_tree_lookup(
    canonical: str,
    plan: RuntimeLookupPlan,
    single_syllable_codes: frozenset[str] | None = None,
) -> str:
    normalized_canonical = str(canonical or "").strip()
    if not normalized_canonical:
        return ""
    if not single_syllable_codes and len(normalized_canonical) < 4:
        return normalized_canonical
    if plan.stage == "C":
        return plan.context_code
    if should_expand_phrase_prefix(plan):
        return plan.lookup_code
    if plan.trailing_code_count <= 0:
        return ""

    if single_syllable_codes:
        completed_syllables, trailing_prefix = _split_complete_syllables_by_inventory(
            normalized_canonical,
            single_syllable_codes,
        )
    else:
        completed_syllables, trailing_prefix = _split_complete_syllables_by_legacy_width(
            normalized_canonical,
        )
    if not trailing_prefix:
        return ""
    return "".join(completed_syllables[-3:]) + trailing_prefix
