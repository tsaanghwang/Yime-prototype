from __future__ import annotations

import math
from dataclasses import dataclass, replace
from enum import Enum
from typing import Callable, Iterable, Mapping, Protocol, Sequence

from .runtime_ranking import RuntimeCandidateRecord, rank_runtime_candidates


class CandidateLayer(str, Enum):
    FOUNDATION_DECODE = "foundation_decode"
    STATIC_LEXICON = "static_lexicon"
    DYNAMIC_COMPOSITION = "dynamic_composition"
    USER_LEARNING = "user_learning"
    SEMANTIC_RANKING = "semantic_ranking"


@dataclass(frozen=True)
class SemanticRankingContext:
    left_text: str = ""
    right_text: str = ""
    application: str = ""

    @property
    def previous_candidate(self) -> str:
        return self.left_text.strip()


@dataclass(frozen=True)
class DynamicCandidateRequest:
    canonical_input: str
    lookup_code: str
    stage: str
    syllable_count: int


class DynamicCandidateProvider(Protocol):
    def __call__(
        self,
        request: DynamicCandidateRequest,
    ) -> Sequence[dict[str, object]]: ...


@dataclass(frozen=True)
class SemanticCandidateScore:
    text: str
    score: float
    reason: str


class SemanticCandidateRanker(Protocol):
    def score(
        self,
        *,
        lookup_code: str,
        candidates: Sequence[RuntimeCandidateRecord],
        context: SemanticRankingContext,
    ) -> Mapping[str, SemanticCandidateScore]: ...


class LocalSemanticRankingSimulator:
    """Local stand-in for a future remote semantic-ranking service.

    The simulator deliberately learns only observed candidate transitions.  It
    does not infer word boundaries, invent readings, or claim semantic truth.
    """

    def __init__(
        self,
        transition_frequency: Mapping[tuple[str, str, str], int] | None = None,
        *,
        transition_log_weight: float = 100.0,
    ) -> None:
        self.transition_log_weight = float(transition_log_weight)
        self._transition_frequency = dict(transition_frequency or {})

    def replace_transition_frequency(
        self,
        transition_frequency: Mapping[tuple[str, str, str], int],
    ) -> None:
        self._transition_frequency = dict(transition_frequency)

    def remember(
        self,
        previous_text: str,
        lookup_code: str,
        candidate_text: str,
        frequency: int,
    ) -> None:
        key = (
            previous_text.strip(),
            lookup_code.strip(),
            candidate_text.strip(),
        )
        if all(key) and frequency > 0:
            self._transition_frequency[key] = int(frequency)

    def score(
        self,
        *,
        lookup_code: str,
        candidates: Sequence[RuntimeCandidateRecord],
        context: SemanticRankingContext,
    ) -> Mapping[str, SemanticCandidateScore]:
        previous_text = context.previous_candidate
        normalized_lookup = lookup_code.strip()
        if not previous_text or not normalized_lookup:
            return {}

        scores: dict[str, SemanticCandidateScore] = {}
        for candidate in candidates:
            frequency = self._transition_frequency.get(
                (previous_text, normalized_lookup, candidate.text),
                0,
            )
            if frequency <= 0:
                continue
            scores[candidate.text] = SemanticCandidateScore(
                text=candidate.text,
                score=math.log1p(frequency) * self.transition_log_weight,
                reason=f"local-transition:{previous_text}",
            )
        return scores


class LayeredCandidatePipeline:
    """Orchestrate deterministic decode, composition, learning and reranking."""

    def __init__(
        self,
        *,
        semantic_ranker: SemanticCandidateRanker | None = None,
        dynamic_providers: Iterable[DynamicCandidateProvider] = (),
        dynamic_candidate_limit: int = 64,
        dynamic_per_leading_char_limit: int = 8,
    ) -> None:
        self.semantic_ranker = semantic_ranker
        self.dynamic_providers = list(dynamic_providers)
        self.dynamic_candidate_limit = max(int(dynamic_candidate_limit), 1)
        self.dynamic_per_leading_char_limit = max(
            int(dynamic_per_leading_char_limit),
            1,
        )
        self.context = SemanticRankingContext()

    def set_context(
        self,
        *,
        left_text: str = "",
        right_text: str = "",
        application: str = "",
    ) -> None:
        self.context = SemanticRankingContext(
            left_text=left_text,
            right_text=right_text,
            application=application,
        )

    def register_dynamic_provider(
        self,
        provider: DynamicCandidateProvider,
    ) -> None:
        self.dynamic_providers.append(provider)

    def collect_dynamic_candidates(
        self,
        request: DynamicCandidateRequest,
    ) -> list[dict[str, object]]:
        collected: list[dict[str, object]] = []
        for provider in self.dynamic_providers:
            for candidate in provider(request):
                annotated = dict(candidate)
                annotated["_candidate_source"] = "dynamic-composition"
                collected.append(annotated)
        return self._prune_dynamic_candidates(request, collected)

    def _prune_dynamic_candidates(
        self,
        request: DynamicCandidateRequest,
        candidates: Sequence[dict[str, object]],
    ) -> list[dict[str, object]]:
        best_by_text: dict[str, dict[str, object]] = {}
        for candidate in candidates:
            text = str(candidate.get("text", "") or "").strip()
            pinyin = str(candidate.get("pinyin_tone", "") or "").strip()
            if (
                len(text) != request.syllable_count
                or not 2 <= len(text) <= 12
                or (
                    pinyin
                    and len([part for part in pinyin.split(" ") if part])
                    != request.syllable_count
                )
            ):
                continue
            existing = best_by_text.get(text)
            if existing is None or self._dynamic_sort_key(
                candidate
            ) < self._dynamic_sort_key(existing):
                best_by_text[text] = candidate

        ranked = sorted(best_by_text.values(), key=self._dynamic_sort_key)
        result: list[dict[str, object]] = []
        count_by_leading_char: dict[str, int] = {}
        for candidate in ranked:
            text = str(candidate.get("text", "") or "")
            leading_char = text[:1]
            if (
                count_by_leading_char.get(leading_char, 0)
                >= self.dynamic_per_leading_char_limit
            ):
                continue
            count_by_leading_char[leading_char] = (
                count_by_leading_char.get(leading_char, 0) + 1
            )
            result.append(candidate)
            if len(result) >= self.dynamic_candidate_limit:
                break
        return result

    @staticmethod
    def _dynamic_sort_key(
        candidate: Mapping[str, object],
    ) -> tuple[int, int, float, float, str, str]:
        try:
            composition_score = float(
                candidate.get("_composition_score", 0.0) or 0.0
            )
        except (TypeError, ValueError):
            composition_score = 0.0
        try:
            sort_weight = float(candidate.get("sort_weight", 0.0) or 0.0)
        except (TypeError, ValueError):
            sort_weight = 0.0
        try:
            atom_count = int(
                candidate.get(
                    "_precomposition_atom_count",
                    0,
                )
                or 0
            )
        except (TypeError, ValueError):
            atom_count = 0
        return (
            0 if bool(candidate.get("is_common", False)) else 1,
            -atom_count,
            -composition_score,
            -sort_weight,
            str(candidate.get("text", "") or ""),
            str(candidate.get("pinyin_tone", "") or ""),
        )

    def rank(
        self,
        candidates: list[RuntimeCandidateRecord],
        user_freq_by_candidate: Mapping[tuple[str, str], int],
    ) -> list[RuntimeCandidateRecord]:
        base_ranked = rank_runtime_candidates(
            candidates,
            user_freq_by_candidate,
        )
        if self.semantic_ranker is None or not base_ranked:
            return base_ranked

        lookup_code = base_ranked[0].lookup_code
        scores = self.semantic_ranker.score(
            lookup_code=lookup_code,
            candidates=base_ranked,
            context=self.context,
        )
        if not scores:
            return base_ranked

        annotated = [
            replace(
                candidate,
                semantic_score=scores.get(
                    candidate.text,
                    SemanticCandidateScore(candidate.text, 0.0, ""),
                ).score,
                semantic_reason=scores.get(
                    candidate.text,
                    SemanticCandidateScore(candidate.text, 0.0, ""),
                ).reason,
            )
            for candidate in base_ranked
        ]
        base_index = {
            candidate.text: index
            for index, candidate in enumerate(base_ranked)
        }
        annotated.sort(
            key=lambda candidate: (
                -candidate.semantic_score,
                base_index[candidate.text],
            )
        )
        return annotated
