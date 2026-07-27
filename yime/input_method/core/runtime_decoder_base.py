from __future__ import annotations

from functools import lru_cache
import json
import os
from pathlib import Path
import unicodedata
from dataclasses import dataclass
from typing import Dict, List, Tuple, cast

from yime.canonical_yime_mapping import (
    convert_legacy_code_to_primary,
    load_code_mode_map,
    load_primary_code_map,
)
from yime.utils.code_modes import YimeCodeMode, code_mode_label, normalize_code_mode
from .runtime_lookup import (
    RuntimeLookupPlan,
    build_runtime_lookup_plan,
    build_runtime_mode_hint,
)
from .layered_candidate_pipeline import (
    DynamicCandidateProvider,
    DynamicCandidateRequest,
    LayeredCandidatePipeline,
    LocalSemanticRankingSimulator,
)
from .bounded_character_composition import (
    BoundedCharacterCompositionProvider,
)
from .neutral_tone_fallback import NeutralToneFallbackProvider
from .recursive_precomposition import RecursivePrecompositionProvider
from .runtime_ranking import (
    apply_stage_b_rare_representative_guardrail,
    RuntimeCandidateRecord,
    build_runtime_candidate_records,
    format_runtime_debug_summary,
    load_local_phrase_priority_rules,
    rank_runtime_candidates,
)
from ..utils.user_lexicon import UserLexiconStore


@dataclass(frozen=True)
class PendingSentenceSelection:
    text: str
    pinyin_tone: str


def canonicalize_runtime_input(text: str, bmp_to_canonical: Dict[str, str]) -> str:
    return "".join(bmp_to_canonical.get(char, char) for char in text)


def _normalize_legacy_runtime_code(code: str, bmp_to_canonical: Dict[str, str]) -> str:
    return convert_legacy_code_to_primary(canonicalize_runtime_input(code, bmp_to_canonical))


@lru_cache(maxsize=None)
def load_numeric_to_marked_pinyin_map(mapping_path: str) -> Dict[str, str]:
    payload = json.loads(Path(mapping_path).read_text(encoding="utf-8"))
    return {
        str(numeric).strip(): unicodedata.normalize("NFC", str(marked))
        for numeric, marked in payload.items()
        if str(numeric).strip() and str(marked).strip()
    }


def format_marked_pinyin_display(
    numeric_pinyin: str,
    numeric_to_marked: Dict[str, str],
) -> str:
    normalized = " ".join(str(numeric_pinyin or "").split())
    if not normalized:
        return ""

    return " ".join(
        numeric_to_marked.get(syllable, syllable)
        for syllable in normalized.split(" ")
    )


def build_pinyin_to_canonical_code_map(
    repo_root: Path,
    bmp_to_canonical: Dict[str, str],
) -> Dict[str, str]:
    return {
        pinyin_tone: canonicalize_runtime_input(runtime_code, bmp_to_canonical)
        for pinyin_tone, runtime_code in load_primary_code_map(repo_root).items()
    }


def build_pinyin_to_code_mode_maps(
    repo_root: Path,
    bmp_to_canonical: Dict[str, str],
) -> Dict[YimeCodeMode, Dict[str, str]]:
    grouped: Dict[YimeCodeMode, Dict[str, str]] = {
        YimeCodeMode.FULL: {},
        YimeCodeMode.VARIABLE: {},
        YimeCodeMode.SHORTHAND: {},
    }
    for pinyin_tone, record in load_code_mode_map(repo_root).items():
        grouped[YimeCodeMode.FULL][pinyin_tone] = canonicalize_runtime_input(
            record.full_code,
            bmp_to_canonical,
        )
        grouped[YimeCodeMode.VARIABLE][pinyin_tone] = canonicalize_runtime_input(
            record.variable_code,
            bmp_to_canonical,
        )
        grouped[YimeCodeMode.SHORTHAND][pinyin_tone] = canonicalize_runtime_input(
            record.shorthand_code,
            bmp_to_canonical,
        )
    return grouped


def resolve_canonical_code_from_pinyin_tone(
    pinyin_tone: str,
    pinyin_to_canonical: Dict[str, str],
) -> str:
    syllables = [syllable for syllable in pinyin_tone.split() if syllable]
    if not syllables:
        return ""

    canonical_parts: List[str] = []
    for syllable in syllables:
        canonical_code = pinyin_to_canonical.get(syllable)
        if not canonical_code:
            return ""
        canonical_parts.append(canonical_code)
    return "".join(canonical_parts)


def merge_runtime_candidate_maps(
    base_by_code: Dict[str, List[Dict[str, object]]],
    overlay_by_code: Dict[str, List[Dict[str, object]]],
) -> Dict[str, List[Dict[str, object]]]:
    merged = {code: list(candidates) for code, candidates in base_by_code.items()}
    for code, candidates in overlay_by_code.items():
        merged.setdefault(code, []).extend(candidates)
    return merged


class RuntimeDecoderBase:
    """Shared runtime-decoder pipeline independent from the backing store."""

    runtime_source_label = "运行时编码表"

    def _load_json(self, path: Path) -> Dict[str, object]:
        with path.open("r", encoding="utf-8") as handle:
            return cast(Dict[str, object], json.load(handle))

    def _build_bmp_to_canonical_map(
        self, projection_path: Path, key_to_symbol_path: Path
    ) -> Dict[str, str]:
        projection = self._load_json(projection_path)
        key_to_symbol = cast(Dict[str, str], self._load_json(key_to_symbol_path))
        bmp_to_canonical: Dict[str, str] = {}

        used_mapping = cast(Dict[str, Dict[str, object]], projection["used_mapping"])

        for yinyuan_id, projection_info in used_mapping.items():
            bmp_char = cast(str, projection_info["char"])
            canonical_char = key_to_symbol.get(yinyuan_id)
            if canonical_char:
                bmp_to_canonical[bmp_char] = canonical_char

        return bmp_to_canonical

    def _init_runtime_decoder_common(
        self,
        app_dir: Path,
        user_db_path: Path | None = None,
    ) -> None:
        self.bmp_to_canonical = self._build_bmp_to_canonical_map(
            app_dir.parent / "internal_data" / "bmp_pua_trial_projection.json",
            app_dir.parent / "internal_data" / "key_to_symbol.json",
        )
        self.code_mode = YimeCodeMode.VARIABLE
        self.pinyin_to_code_by_mode = build_pinyin_to_code_mode_maps(
            app_dir.parent,
            self.bmp_to_canonical,
        )
        self.pinyin_to_canonical = self.pinyin_to_code_by_mode[YimeCodeMode.VARIABLE]
        self.numeric_to_marked_pinyin = load_numeric_to_marked_pinyin_map(
            str(app_dir / "pinyin_normalized.json")
        )
        self._local_phrase_priority_rules = load_local_phrase_priority_rules(
            app_dir.parent / "internal_data" / "local_phrase_priority_rules.json",
            self.pinyin_to_canonical,
            resolve_canonical_code_from_pinyin_tone,
        )
        self.single_syllable_codes = frozenset(
            code for code in self.pinyin_to_canonical.values() if str(code or "").strip()
        )
        self._continuous_input_priority_rules = load_local_phrase_priority_rules(
            app_dir.parent / "internal_data" / "continuous_input_priority_rules.json",
            self.pinyin_to_canonical,
            resolve_canonical_code_from_pinyin_tone,
            expected_lookup_code_length=None,
            min_lookup_code_length=5,
            normalize_lookup_code=lambda code: _normalize_legacy_runtime_code(
                code,
                self.bmp_to_canonical,
            ),
        )
        self.user_lexicon = UserLexiconStore(user_db_path or app_dir / "user_lexicon.db")
        self._user_freq_by_candidate = self.user_lexicon.load_candidate_frequency()
        self._local_semantic_ranker = LocalSemanticRankingSimulator(
            self.user_lexicon.load_candidate_transition_frequency()
        )
        self._candidate_pipeline = LayeredCandidatePipeline(
            semantic_ranker=self._local_semantic_ranker,
        )
        self._last_ranked_candidates_by_text: Dict[
            str,
            RuntimeCandidateRecord,
        ] = {}
        self._pending_sentence_selections: List[
            PendingSentenceSelection
        ] = []
        self.debug_runtime_ranking = os.environ.get(
            "YIME_DEBUG_RUNTIME_RANKING",
            "",
        ).strip().lower() in {"1", "true", "yes", "on"}

    def _install_builtin_dynamic_candidate_providers(self) -> None:
        self.register_dynamic_candidate_provider(
            RecursivePrecompositionProvider(
                get_pinyin_to_code=lambda: self.pinyin_to_canonical,
                get_component_candidates=(
                    self.get_precomposition_candidates
                ),
            )
        )
        self.register_dynamic_candidate_provider(
            BoundedCharacterCompositionProvider(
                get_pinyin_to_code=lambda: self.pinyin_to_canonical,
                get_char_candidates=self.get_char_candidates,
            )
        )
        self.register_dynamic_candidate_provider(
            NeutralToneFallbackProvider(
                get_pinyin_to_code=lambda: self.pinyin_to_canonical,
                get_char_candidates=self.get_char_candidates,
            )
        )

    def set_code_mode(self, mode: YimeCodeMode | str | object) -> None:
        self.code_mode = normalize_code_mode(mode)
        mode_map = getattr(self, "pinyin_to_code_by_mode", {})
        self.pinyin_to_canonical = mode_map.get(self.code_mode, getattr(self, "pinyin_to_canonical", {}))
        self.single_syllable_codes = frozenset(
            code for code in self.pinyin_to_canonical.values() if str(code or "").strip()
        )

    def get_code_mode(self) -> YimeCodeMode:
        return normalize_code_mode(getattr(self, "code_mode", YimeCodeMode.VARIABLE))

    def _lookup_runtime_candidates_for_decode(
        self,
        canonical: str,
        plan: RuntimeLookupPlan,
    ) -> tuple[List[Dict[str, object]], str]:
        raise NotImplementedError

    def get_precomposition_candidates(
        self,
        code: str,
        syllable_count: int,
    ) -> List[Dict[str, object]]:
        """Return exact, already encoded components for recursive assembly."""

        if int(syllable_count) != 1:
            return []
        return [
            {
                "text": candidate.text,
                "entry_type": "char",
                "entry_id": candidate.entry_id,
                "pinyin_tone": candidate.pinyin_tone,
                "yime_code": candidate.code,
                "primary_yime_code": candidate.code,
                "sort_weight": candidate.sort_weight,
                "is_common": candidate.is_common,
                "text_length": 1,
            }
            for candidate in self.get_char_candidates(code)
        ]

    def decode_text(
        self, text: str
    ) -> Tuple[str, str, str, List[str], str]:
        canonical = canonicalize_runtime_input(text, self.bmp_to_canonical)
        if not canonical:
            return "", "", "", [], "请输入一个完整音节的编码。"

        single_syllable_codes = getattr(self, "single_syllable_codes", None)
        plan = build_runtime_lookup_plan(canonical, single_syllable_codes)
        mode_hint = build_runtime_mode_hint(canonical, plan, single_syllable_codes)
        raw_candidates, priority_lookup_code = self._lookup_runtime_candidates_for_decode(
            canonical,
            plan,
        )
        candidate_pipeline = getattr(self, "_candidate_pipeline", None)
        if candidate_pipeline is not None:
            raw_candidates.extend(
                candidate_pipeline.collect_dynamic_candidates(
                    DynamicCandidateRequest(
                        canonical_input=canonical,
                        lookup_code=plan.lookup_code,
                        stage=plan.stage,
                        syllable_count=plan.syllable_count,
                    )
                )
            )
        records = self._rank_runtime_candidates(
            self._payload_to_runtime_candidates(
                plan.lookup_code,
                raw_candidates,
                stage=plan.stage,
                priority_lookup_code=priority_lookup_code,
            )
        )
        if plan.stage == "B":
            records = apply_stage_b_rare_representative_guardrail(records)
        self._last_ranked_candidates_by_text = {
            record.text: record
            for record in records
        }
        texts = [record.text for record in records]
        pinyin_values: List[str] = []
        numeric_to_marked_pinyin = getattr(self, "numeric_to_marked_pinyin", {})
        for record in records:
            display_pinyin = format_marked_pinyin_display(
                record.pinyin_tone,
                numeric_to_marked_pinyin,
            )
            if display_pinyin and display_pinyin not in pinyin_values:
                pinyin_values.append(display_pinyin)

        display_pinyin = " / ".join(pinyin_values[:3])
        if texts:
            status = f"{code_mode_label(self.get_code_mode())}：从{self.runtime_source_label}找到 {len(texts)} 个候选。"
            debug_summary = format_runtime_debug_summary(records)
            if getattr(self, "debug_runtime_ranking", False) and debug_summary:
                pool_hint = ""
                if plan.phrase_prefix_pool:
                    pool_hint = f"[{plan.phrase_prefix_pool}] "
                status = f"{status} 调试: {pool_hint}{debug_summary}。"
            if mode_hint:
                status = f"{mode_hint} {status}"
            return canonical, plan.active_code, display_pinyin, texts, status

        if plan.stage == "A":
            status = mode_hint or "当前输入尚未形成完整音节，继续输入。"
            return canonical, canonical, display_pinyin, [], status

        if plan.phrase_mode:
            status = f"{self.runtime_source_label}中未找到该 {plan.syllable_count} 音节词语候选。"
        else:
            status = f"{self.runtime_source_label}中未找到该音节编码候选。"
        status = f"{code_mode_label(self.get_code_mode())}：{status}"
        if mode_hint:
            status = f"{mode_hint} {status}"
        return canonical, plan.active_code, display_pinyin, [], status

    def record_selection(self, text: str, candidate_text: str) -> int:
        canonical = canonicalize_runtime_input(text, self.bmp_to_canonical)
        plan = build_runtime_lookup_plan(
            canonical,
            getattr(self, "single_syllable_codes", None),
        )
        if not plan.lookup_code or not candidate_text.strip():
            return 0
        key = (plan.lookup_code, candidate_text.strip())
        user_lexicon = getattr(self, "user_lexicon", None)
        if user_lexicon is None:
            persisted_freq = int(self._user_freq_by_candidate.get(key, 0)) + 1
        else:
            persisted_freq = user_lexicon.record_candidate_selection(*key)
        self._user_freq_by_candidate[key] = persisted_freq
        candidate_pipeline = getattr(self, "_candidate_pipeline", None)
        previous_text = (
            candidate_pipeline.context.previous_candidate
            if candidate_pipeline is not None
            else ""
        )
        if previous_text and user_lexicon is not None:
            transition_frequency = user_lexicon.record_candidate_transition(
                previous_text,
                plan.lookup_code,
                candidate_text,
            )
            local_ranker = getattr(self, "_local_semantic_ranker", None)
            if local_ranker is not None:
                local_ranker.remember(
                    previous_text,
                    plan.lookup_code,
                    candidate_text,
                    transition_frequency,
                )
        if candidate_pipeline is not None:
            candidate_pipeline.set_context(left_text=candidate_text)
        selected_record = getattr(
            self,
            "_last_ranked_candidates_by_text",
            {},
        ).get(candidate_text.strip())
        if selected_record is not None:
            pinyin_parts = [
                part
                for part in selected_record.pinyin_tone.split(" ")
                if part
            ]
            if (
                selected_record.text
                and len(selected_record.text) == len(pinyin_parts)
                and 1 <= len(selected_record.text) <= 12
            ):
                pending_selections = getattr(
                    self,
                    "_pending_sentence_selections",
                    None,
                )
                if pending_selections is None:
                    pending_selections = []
                    self._pending_sentence_selections = pending_selections
                pending_selections.append(
                    PendingSentenceSelection(
                        text=selected_record.text,
                        pinyin_tone=" ".join(pinyin_parts),
                    )
                )
        return persisted_freq

    def record_sentence_commit(self, committed_text: str) -> bool:
        selections = list(
            getattr(self, "_pending_sentence_selections", [])
        )
        self._pending_sentence_selections = []
        normalized_text = committed_text.strip()
        if (
            not selections
            or "".join(item.text for item in selections) != normalized_text
            or not 2 <= len(normalized_text) <= 12
        ):
            return False

        numeric_pinyin = " ".join(
            item.pinyin_tone
            for item in selections
        )
        numeric_parts = [
            part
            for part in numeric_pinyin.split(" ")
            if part
        ]
        if len(numeric_parts) != len(normalized_text):
            return False

        full_code = resolve_canonical_code_from_pinyin_tone(
            numeric_pinyin,
            self.pinyin_to_code_by_mode[YimeCodeMode.FULL],
        )
        current_code = resolve_canonical_code_from_pinyin_tone(
            numeric_pinyin,
            self.pinyin_to_canonical,
        )
        if not full_code or not current_code:
            return False

        marked_pinyin = format_marked_pinyin_display(
            numeric_pinyin,
            getattr(self, "numeric_to_marked_pinyin", {}),
        )
        self.user_lexicon.upsert_phrase(
            normalized_text,
            numeric_pinyin,
            marked_pinyin=marked_pinyin,
            yime_code=full_code,
            source_note="auto_learned_committed_sentence",
        )
        persisted_freq = self.user_lexicon.record_candidate_selection(
            current_code,
            normalized_text,
        )
        self._user_freq_by_candidate[
            (current_code, normalized_text)
        ] = persisted_freq
        self.reload_user_lexicon()
        return True

    def set_semantic_context(
        self,
        left_text: str = "",
        *,
        right_text: str = "",
        application: str = "",
    ) -> None:
        candidate_pipeline = getattr(self, "_candidate_pipeline", None)
        if candidate_pipeline is not None:
            candidate_pipeline.set_context(
                left_text=left_text,
                right_text=right_text,
                application=application,
            )

    def clear_semantic_context(self) -> None:
        self.set_semantic_context()

    def register_dynamic_candidate_provider(
        self,
        provider: DynamicCandidateProvider,
    ) -> None:
        candidate_pipeline = getattr(self, "_candidate_pipeline", None)
        if candidate_pipeline is None:
            candidate_pipeline = LayeredCandidatePipeline()
            self._candidate_pipeline = candidate_pipeline
        candidate_pipeline.register_dynamic_provider(provider)

    def _refresh_layered_pipeline_learning(self) -> None:
        user_lexicon = getattr(self, "user_lexicon", None)
        local_ranker = getattr(self, "_local_semantic_ranker", None)
        if user_lexicon is not None and local_ranker is not None:
            local_ranker.replace_transition_frequency(
                user_lexicon.load_candidate_transition_frequency()
            )

    def _payload_to_runtime_candidates(
        self,
        lookup_code: str,
        raw_candidates: List[Dict[str, object]],
        stage: str = "",
        priority_lookup_code: str = "",
    ) -> List[RuntimeCandidateRecord]:
        return build_runtime_candidate_records(
            lookup_code,
            raw_candidates,
            stage=stage,
            priority_lookup_code=priority_lookup_code,
            char_sort_weight_by_text=getattr(self, "_char_sort_weight_by_text", {}),
            local_phrase_priority_rules=getattr(self, "_local_phrase_priority_rules", {}),
            continuous_input_priority_rules=getattr(self, "_continuous_input_priority_rules", {}),
        )

    def _rank_runtime_candidates(
        self,
        candidates: List[RuntimeCandidateRecord],
    ) -> List[RuntimeCandidateRecord]:
        candidate_pipeline = getattr(self, "_candidate_pipeline", None)
        if candidate_pipeline is not None:
            return candidate_pipeline.rank(
                candidates,
                self._user_freq_by_candidate,
            )
        return rank_runtime_candidates(candidates, self._user_freq_by_candidate)
