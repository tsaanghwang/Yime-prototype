"""Bounded dynamic composition for attested neutral-tone syllables.

This module does not add a neutral-tone reading to any character.  It only
allows an attested base-tone character reading to occupy the corresponding
neutral-tone slot while composing a multi-character runtime candidate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

from .char_code_index import CharCodeCandidate
from .layered_candidate_pipeline import DynamicCandidateRequest
from .runtime_lookup import split_complete_syllables


MIN_SYLLABLE_COUNT = 2
MAX_SYLLABLE_COUNT = 7
DEFAULT_CANDIDATES_PER_SYLLABLE = 12
DEFAULT_BEAM_WIDTH = 96
DEFAULT_RESULT_LIMIT = 64
NEUTRAL_FALLBACK_WEIGHT_FACTOR = 0.01


def _numeric_base(pinyin_tone: str) -> str:
    normalized = str(pinyin_tone or "").strip().lower()
    if normalized[-1:] in {"1", "2", "3", "4", "5"}:
        return normalized[:-1]
    return ""


def _is_base_tone_reading(pinyin_tone: str, expected_base: str) -> bool:
    normalized = str(pinyin_tone or "").strip().lower()
    return (
        normalized[-1:] in {"1", "2", "3", "4"}
        and _numeric_base(normalized) == expected_base
    )


@dataclass(frozen=True)
class _SlotCandidate:
    char: CharCodeCandidate
    output_pinyin: str
    uses_neutral_fallback: bool


@dataclass(frozen=True)
class _BeamState:
    text: str
    pinyin: tuple[str, ...]
    score: float
    is_common: bool
    fallback_count: int


class NeutralToneFallbackProvider:
    """Compose phrases by projecting base-tone chars into neutral-tone slots."""

    def __init__(
        self,
        *,
        get_pinyin_to_code: Callable[[], Mapping[str, str]],
        get_char_candidates: Callable[[str], Sequence[CharCodeCandidate]],
        candidates_per_syllable: int = DEFAULT_CANDIDATES_PER_SYLLABLE,
        beam_width: int = DEFAULT_BEAM_WIDTH,
        result_limit: int = DEFAULT_RESULT_LIMIT,
    ) -> None:
        self._get_pinyin_to_code = get_pinyin_to_code
        self._get_char_candidates = get_char_candidates
        self.candidates_per_syllable = max(int(candidates_per_syllable), 1)
        self.beam_width = max(int(beam_width), 1)
        self.result_limit = max(int(result_limit), 1)

    def __call__(
        self,
        request: DynamicCandidateRequest,
    ) -> Sequence[dict[str, object]]:
        if (
            request.stage != "D"
            or not MIN_SYLLABLE_COUNT
            <= int(request.syllable_count)
            <= MAX_SYLLABLE_COUNT
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

        pinyins_by_code: dict[str, list[str]] = {}
        for pinyin, code in pinyin_to_code.items():
            pinyins_by_code.setdefault(code, []).append(pinyin)

        slots: list[list[_SlotCandidate]] = []
        has_fallback_slot = False
        for code in syllable_codes:
            exact = list(self._get_char_candidates(code))
            options = self._exact_slot_candidates(
                exact,
                pinyins_by_code.get(code, ()),
            )
            fallback = self._neutral_fallback_candidates(
                code,
                pinyins_by_code,
                pinyin_to_code,
            )
            if fallback:
                has_fallback_slot = True
                options.extend(fallback)
            options = self._deduplicate_and_limit(options)
            if not options:
                return []
            slots.append(options)

        if not has_fallback_slot:
            return []

        beam = [
            _BeamState(
                text="",
                pinyin=(),
                score=0.0,
                is_common=True,
                fallback_count=0,
            )
        ]
        for options in slots:
            expanded: list[_BeamState] = []
            for state in beam:
                for option in options:
                    expanded.append(
                        _BeamState(
                            text=state.text + option.char.text,
                            pinyin=(*state.pinyin, option.output_pinyin),
                            score=state.score
                            + math.log1p(max(option.char.sort_weight, 0.0)),
                            is_common=state.is_common and option.char.is_common,
                            fallback_count=state.fallback_count
                            + int(option.uses_neutral_fallback),
                        )
                    )
            beam = self._prune_beam(expanded)

        results: list[dict[str, object]] = []
        seen_texts: set[str] = set()
        for state in sorted(
            (item for item in beam if item.fallback_count > 0),
            key=lambda item: (
                item.fallback_count,
                -item.score,
                item.text,
                item.pinyin,
            ),
        ):
            if state.text in seen_texts:
                continue
            seen_texts.add(state.text)
            results.append(
                {
                    "text": state.text,
                    "entry_type": "phrase",
                    "entry_id": f"neutral-tone-fallback:{state.text}",
                    "pinyin_tone": " ".join(state.pinyin),
                    "yime_code": request.lookup_code,
                    "primary_yime_code": request.lookup_code,
                    "sort_weight": (
                        state.score * NEUTRAL_FALLBACK_WEIGHT_FACTOR
                    ),
                    "is_common": state.is_common,
                    "text_length": len(state.text),
                    "_neutral_tone_fallback_count": state.fallback_count,
                    "_composition_score": state.score,
                    "_composition_rule": "attested_neutral_tone_fallback",
                }
            )
            if len(results) >= self.result_limit:
                break
        return results

    @staticmethod
    def _exact_slot_candidates(
        candidates: Sequence[CharCodeCandidate],
        code_pinyins: Sequence[str],
    ) -> list[_SlotCandidate]:
        fallback_pinyin = sorted(code_pinyins)[0] if code_pinyins else ""
        return [
            _SlotCandidate(
                char=candidate,
                output_pinyin=(
                    str(candidate.pinyin_tone or "").strip() or fallback_pinyin
                ),
                uses_neutral_fallback=False,
            )
            for candidate in candidates
            if len(candidate.text) == 1
        ]

    def _neutral_fallback_candidates(
        self,
        neutral_code: str,
        pinyins_by_code: Mapping[str, Sequence[str]],
        pinyin_to_code: Mapping[str, str],
    ) -> list[_SlotCandidate]:
        results: list[_SlotCandidate] = []
        neutral_pinyins = sorted(
            pinyin
            for pinyin in pinyins_by_code.get(neutral_code, ())
            if pinyin.endswith("5") and _numeric_base(pinyin)
        )
        for neutral_pinyin in neutral_pinyins:
            base = _numeric_base(neutral_pinyin)
            for tone in "1234":
                base_pinyin = f"{base}{tone}"
                base_code = pinyin_to_code.get(base_pinyin)
                if not base_code:
                    continue
                for candidate in self._get_char_candidates(base_code):
                    if (
                        len(candidate.text) == 1
                        and _is_base_tone_reading(candidate.pinyin_tone, base)
                    ):
                        results.append(
                            _SlotCandidate(
                                char=candidate,
                                output_pinyin=neutral_pinyin,
                                uses_neutral_fallback=True,
                            )
                        )
        return results

    def _deduplicate_and_limit(
        self,
        candidates: Sequence[_SlotCandidate],
    ) -> list[_SlotCandidate]:
        best_by_key: dict[tuple[str, bool], _SlotCandidate] = {}
        for candidate in candidates:
            key = (candidate.char.text, candidate.uses_neutral_fallback)
            existing = best_by_key.get(key)
            if (
                existing is None
                or candidate.char.sort_weight > existing.char.sort_weight
            ):
                best_by_key[key] = candidate
        ranking_key = lambda item: (
            -item.char.sort_weight,
            item.char.text,
            item.output_pinyin,
        )
        exact = sorted(
            (
                item
                for item in best_by_key.values()
                if not item.uses_neutral_fallback
            ),
            key=ranking_key,
        )
        fallback = sorted(
            (
                item
                for item in best_by_key.values()
                if item.uses_neutral_fallback
            ),
            key=ranking_key,
        )
        if not exact or not fallback:
            return (exact or fallback)[: self.candidates_per_syllable]

        fallback_limit = max(self.candidates_per_syllable // 2, 1)
        exact_limit = max(self.candidates_per_syllable - fallback_limit, 1)
        return [
            *exact[:exact_limit],
            *fallback[:fallback_limit],
        ][: self.candidates_per_syllable]

    def _prune_beam(self, expanded: Sequence[_BeamState]) -> list[_BeamState]:
        ranking_key = lambda state: (
            state.fallback_count,
            -state.score,
            state.text,
            state.pinyin,
        )
        without_fallback = sorted(
            (state for state in expanded if state.fallback_count == 0),
            key=ranking_key,
        )
        with_fallback = sorted(
            (state for state in expanded if state.fallback_count > 0),
            key=ranking_key,
        )
        if not without_fallback or not with_fallback:
            return (without_fallback or with_fallback)[: self.beam_width]

        fallback_limit = max(self.beam_width // 2, 1)
        exact_limit = max(self.beam_width - fallback_limit, 1)
        return [
            *without_fallback[:exact_limit],
            *with_fallback[:fallback_limit],
        ][: self.beam_width]
