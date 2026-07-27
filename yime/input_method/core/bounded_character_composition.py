"""Bounded single-character composition for complete runtime syllables."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

from .char_code_index import CharCodeCandidate
from .layered_candidate_pipeline import DynamicCandidateRequest
from .runtime_lookup import split_complete_syllables


MIN_COMPOSITION_SYLLABLES = 2
MAX_COMPOSITION_SYLLABLES = 7
DEFAULT_SLOT_LIMIT = 8
DEFAULT_BEAM_WIDTH = 96
DEFAULT_RESULT_LIMIT = 64


@dataclass(frozen=True)
class _CompositionState:
    text: str
    pinyin: tuple[str, ...]
    components: tuple[str, ...]
    score: float
    common_count: int


class BoundedCharacterCompositionProvider:
    """Compose complete inputs without materializing a Cartesian product."""

    def __init__(
        self,
        *,
        get_pinyin_to_code: Callable[[], Mapping[str, str]],
        get_char_candidates: Callable[[str], Sequence[CharCodeCandidate]],
        slot_limit: int = DEFAULT_SLOT_LIMIT,
        beam_width: int = DEFAULT_BEAM_WIDTH,
        result_limit: int = DEFAULT_RESULT_LIMIT,
    ) -> None:
        self._get_pinyin_to_code = get_pinyin_to_code
        self._get_char_candidates = get_char_candidates
        self.slot_limit = max(int(slot_limit), 1)
        self.beam_width = max(int(beam_width), 1)
        self.result_limit = max(int(result_limit), 1)

    def __call__(
        self,
        request: DynamicCandidateRequest,
    ) -> Sequence[dict[str, object]]:
        if (
            request.stage != "D"
            or not MIN_COMPOSITION_SYLLABLES
            <= int(request.syllable_count)
            <= MAX_COMPOSITION_SYLLABLES
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

        slots: list[list[CharCodeCandidate]] = []
        for code in syllable_codes:
            candidates = self._deduplicate_chars(
                self._get_char_candidates(code)
            )
            if not candidates:
                return []
            slots.append(candidates[: self.slot_limit])

        beam = [
            _CompositionState(
                text="",
                pinyin=(),
                components=(),
                score=0.0,
                common_count=0,
            )
        ]
        for code, candidates in zip(syllable_codes, slots):
            fallback_pinyin = sorted(pinyins_by_code.get(code, ()))[0]
            expanded: list[_CompositionState] = []
            for state in beam:
                for candidate in candidates:
                    pinyin = (
                        str(candidate.pinyin_tone or "").strip()
                        or fallback_pinyin
                    )
                    expanded.append(
                        _CompositionState(
                            text=state.text + candidate.text,
                            pinyin=(*state.pinyin, pinyin),
                            components=(
                                *state.components,
                                f"{candidate.text}/{pinyin}",
                            ),
                            score=state.score
                            + math.log1p(max(candidate.sort_weight, 0.0)),
                            common_count=state.common_count
                            + int(candidate.is_common),
                        )
                    )
            expanded.sort(
                key=lambda state: (
                    -state.common_count,
                    -state.score,
                    state.text,
                    state.pinyin,
                )
            )
            beam = expanded[: self.beam_width]

        results: list[dict[str, object]] = []
        for state in beam[: self.result_limit]:
            results.append(
                {
                    "text": state.text,
                    "entry_type": "phrase",
                    "entry_id": f"bounded-char-composition:{state.text}",
                    "pinyin_tone": " ".join(state.pinyin),
                    "yime_code": request.lookup_code,
                    "primary_yime_code": request.lookup_code,
                    "sort_weight": state.score,
                    "is_common": state.common_count == request.syllable_count,
                    "text_length": len(state.text),
                    "_composition_score": state.score,
                    "_composition_components": list(state.components),
                    "_composition_rule": "bounded_single_character_beam",
                }
            )
        return results

    @staticmethod
    def _deduplicate_chars(
        candidates: Sequence[CharCodeCandidate],
    ) -> list[CharCodeCandidate]:
        best_by_text: dict[str, CharCodeCandidate] = {}
        for candidate in candidates:
            if len(candidate.text) != 1:
                continue
            existing = best_by_text.get(candidate.text)
            if (
                existing is None
                or candidate.sort_weight > existing.sort_weight
            ):
                best_by_text[candidate.text] = candidate
        return sorted(
            best_by_text.values(),
            key=lambda candidate: (
                not candidate.is_common,
                -candidate.sort_weight,
                candidate.text,
                candidate.pinyin_tone,
            ),
        )
