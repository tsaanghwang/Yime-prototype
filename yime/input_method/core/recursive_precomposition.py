"""Bounded recursive composition from encoded runtime components.

The provider treats attested one-to-four-character candidates as reusable
components.  A partial result produced at one boundary remains in the chart
and can therefore participate in later composition steps.  Longer candidates
are admitted only when the backing store explicitly marks them as
precomposition atoms; this is the escape hatch for indivisible lianmian and
multi-syllable transliteration units.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

from .layered_candidate_pipeline import DynamicCandidateRequest
from .runtime_lookup import split_complete_syllables


MIN_RECURSIVE_SYLLABLES = 2
MAX_RECURSIVE_SYLLABLES = 12
DEFAULT_COMPONENT_MAX_SYLLABLES = 4
DEFAULT_COMPONENT_SLOT_LIMIT = 12
DEFAULT_CHART_BEAM_WIDTH = 256
DEFAULT_RESULT_LIMIT = 96
DEFAULT_COMPONENT_PENALTY = 0.75
DEFAULT_MULTICHAR_BONUS = 0.6
DEFAULT_ATOM_BONUS = 2.0


@dataclass(frozen=True)
class _Component:
    text: str
    pinyin: tuple[str, ...]
    score: float
    raw_weight: float
    is_common: bool
    is_atom: bool
    source: str


@dataclass(frozen=True)
class _RecursiveState:
    text: str
    pinyin: tuple[str, ...]
    components: tuple[str, ...]
    score: float
    common_count: int
    atom_count: int
    atom_weight: float


class RecursivePrecompositionProvider:
    """Compose a complete input through reusable, source-backed components."""

    def __init__(
        self,
        *,
        get_pinyin_to_code: Callable[[], Mapping[str, str]],
        get_component_candidates: Callable[
            [str, int], Sequence[Mapping[str, object]]
        ],
        component_max_syllables: int = DEFAULT_COMPONENT_MAX_SYLLABLES,
        component_slot_limit: int = DEFAULT_COMPONENT_SLOT_LIMIT,
        chart_beam_width: int = DEFAULT_CHART_BEAM_WIDTH,
        result_limit: int = DEFAULT_RESULT_LIMIT,
        component_penalty: float = DEFAULT_COMPONENT_PENALTY,
        multichar_bonus: float = DEFAULT_MULTICHAR_BONUS,
        atom_bonus: float = DEFAULT_ATOM_BONUS,
    ) -> None:
        self._get_pinyin_to_code = get_pinyin_to_code
        self._get_component_candidates = get_component_candidates
        self.component_max_syllables = max(
            int(component_max_syllables), 1
        )
        self.component_slot_limit = max(int(component_slot_limit), 1)
        self.chart_beam_width = max(int(chart_beam_width), 1)
        self.result_limit = max(int(result_limit), 1)
        self.component_penalty = float(component_penalty)
        self.multichar_bonus = float(multichar_bonus)
        self.atom_bonus = float(atom_bonus)

    def __call__(
        self,
        request: DynamicCandidateRequest,
    ) -> Sequence[dict[str, object]]:
        if (
            request.stage != "D"
            or not MIN_RECURSIVE_SYLLABLES
            <= int(request.syllable_count)
            <= MAX_RECURSIVE_SYLLABLES
        ):
            return []

        pinyin_to_code = {
            str(pinyin).strip().lower(): str(code).strip()
            for pinyin, code in self._get_pinyin_to_code().items()
            if str(pinyin).strip() and str(code).strip()
        }
        code_inventory = frozenset(pinyin_to_code.values())
        syllable_codes = split_complete_syllables(
            request.lookup_code,
            code_inventory,
        )
        if len(syllable_codes) != request.syllable_count:
            return []

        pinyins_by_code: dict[str, tuple[str, ...]] = {}
        grouped_pinyins: dict[str, list[str]] = {}
        for pinyin, code in pinyin_to_code.items():
            grouped_pinyins.setdefault(code, []).append(pinyin)
        for code, values in grouped_pinyins.items():
            pinyins_by_code[code] = tuple(sorted(set(values)))

        edges: dict[int, list[tuple[int, _Component]]] = {}
        syllable_count = len(syllable_codes)
        for start in range(syllable_count):
            for end in range(start + 1, syllable_count + 1):
                width = end - start
                lookup_code = "".join(syllable_codes[start:end])
                raw_candidates = self._get_component_candidates(
                    lookup_code,
                    width,
                )
                components = self._normalize_components(
                    raw_candidates,
                    width=width,
                    fallback_pinyin=tuple(
                        pinyins_by_code[code][0]
                        for code in syllable_codes[start:end]
                    ),
                )
                if not components:
                    continue
                edges.setdefault(start, []).extend(
                    (end, component)
                    for component in components
                )

        chart: list[list[_RecursiveState]] = [
            [] for _ in range(syllable_count + 1)
        ]
        chart[0] = [
            _RecursiveState(
                text="",
                pinyin=(),
                components=(),
                score=0.0,
                common_count=0,
                atom_count=0,
                atom_weight=0.0,
            )
        ]
        for start in range(syllable_count):
            if not chart[start]:
                continue
            for end, component in edges.get(start, ()):
                expanded = list(chart[end])
                for state in chart[start]:
                    component_bonus = (
                        self.atom_bonus
                        if component.is_atom
                        else self.multichar_bonus
                        * max(len(component.text) - 1, 0)
                    )
                    expanded.append(
                        _RecursiveState(
                            text=state.text + component.text,
                            pinyin=(*state.pinyin, *component.pinyin),
                            components=(
                                *state.components,
                                (
                                    f"{component.text}/"
                                    f"{' '.join(component.pinyin)}"
                                ),
                            ),
                            score=(
                                state.score
                                + component.score
                                + component_bonus
                                - (
                                    self.component_penalty
                                    if state.components
                                    else 0.0
                                )
                            ),
                            common_count=(
                                state.common_count
                                + (
                                    len(component.text)
                                    if component.is_common
                                    else 0
                                )
                            ),
                            atom_count=(
                                state.atom_count + int(component.is_atom)
                            ),
                            atom_weight=max(
                                state.atom_weight,
                                (
                                    component.raw_weight
                                    if component.is_atom
                                    else 0.0
                                ),
                            ),
                        )
                    )
                chart[end] = self._prune_states(expanded)

        results: list[dict[str, object]] = []
        for state in chart[syllable_count][: self.result_limit]:
            if len(state.text) != syllable_count:
                continue
            results.append(
                {
                    "text": state.text,
                    "entry_type": "phrase",
                    "entry_id": (
                        f"recursive-precomposition:{state.text}"
                    ),
                    "pinyin_tone": " ".join(state.pinyin),
                    "yime_code": request.lookup_code,
                    "primary_yime_code": request.lookup_code,
                    "sort_weight": max(
                        state.score,
                        state.atom_weight,
                    ),
                    "is_common": (
                        state.common_count == syllable_count
                    ),
                    "text_length": len(state.text),
                    "_composition_score": max(
                        state.score,
                        state.atom_weight,
                    ),
                    "_composition_components": list(state.components),
                    "_composition_rule": (
                        "bounded_recursive_precomposition"
                    ),
                    "_precomposition_rounds": max(
                        len(state.components) - 1,
                        1,
                    ),
                    "_precomposition_atom_count": state.atom_count,
                }
            )
        return results

    def _normalize_components(
        self,
        candidates: Sequence[Mapping[str, object]],
        *,
        width: int,
        fallback_pinyin: tuple[str, ...],
    ) -> list[_Component]:
        best_by_text: dict[str, _Component] = {}
        for candidate in candidates:
            text = str(candidate.get("text", "") or "").strip()
            is_atom = bool(
                candidate.get("_precomposition_atom", False)
                or str(candidate.get("entry_type", "") or "").strip()
                == "precomposition_atom"
            )
            if (
                len(text) != width
                or (
                    width > self.component_max_syllables
                    and not is_atom
                )
            ):
                continue
            raw_pinyin = tuple(
                part
                for part in str(
                    candidate.get("pinyin_tone", "") or ""
                ).split()
                if part
            )
            pinyin = (
                raw_pinyin
                if len(raw_pinyin) == width
                else fallback_pinyin
            )
            try:
                weight = float(
                    candidate.get("sort_weight", 0.0) or 0.0
                )
            except (TypeError, ValueError):
                weight = 0.0
            component = _Component(
                text=text,
                pinyin=pinyin,
                score=math.log1p(max(weight, 0.0)),
                raw_weight=max(weight, 0.0),
                is_common=bool(candidate.get("is_common", False)),
                is_atom=is_atom,
                source=str(
                    candidate.get("_candidate_source", "") or ""
                ),
            )
            existing = best_by_text.get(text)
            if (
                existing is None
                or self._component_sort_key(component)
                < self._component_sort_key(existing)
            ):
                best_by_text[text] = component
        return sorted(
            best_by_text.values(),
            key=self._component_sort_key,
        )[: self.component_slot_limit]

    def _prune_states(
        self,
        states: Sequence[_RecursiveState],
    ) -> list[_RecursiveState]:
        best_by_text: dict[str, _RecursiveState] = {}
        for state in states:
            existing = best_by_text.get(state.text)
            if (
                existing is None
                or self._state_sort_key(state)
                < self._state_sort_key(existing)
            ):
                best_by_text[state.text] = state
        return sorted(
            best_by_text.values(),
            key=self._state_sort_key,
        )[: self.chart_beam_width]

    @staticmethod
    def _component_sort_key(
        component: _Component,
    ) -> tuple[int, int, float, str, tuple[str, ...]]:
        return (
            0 if component.is_atom else 1,
            0 if component.is_common else 1,
            -component.score,
            component.text,
            component.pinyin,
        )

    @staticmethod
    def _state_sort_key(
        state: _RecursiveState,
    ) -> tuple[
        int,
        int,
        float,
        int,
        str,
        tuple[str, ...],
    ]:
        return (
            -state.common_count,
            -state.atom_count,
            -state.score,
            len(state.components),
            state.text,
            state.pinyin,
        )
