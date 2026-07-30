from __future__ import annotations

from yime.input_method.core.layered_candidate_pipeline import (
    DynamicCandidateRequest,
    LayeredCandidatePipeline,
    LocalSemanticRankingSimulator,
)
from yime.input_method.core.runtime_ranking import (
    RuntimeCandidateRecord,
    build_runtime_candidate_records,
    rank_runtime_candidates,
)
from yime.input_method.core.runtime_decoder_base import RuntimeDecoderBase
from yime.input_method.utils.user_lexicon import UserLexiconStore


def _candidate(text: str) -> RuntimeCandidateRecord:
    return RuntimeCandidateRecord(
        lookup_code="CODE",
        text=text,
        entry_type="phrase",
        pinyin_tone="test1",
        sort_weight=100.0,
        text_length=len(text),
    )


def test_local_semantic_simulator_promotes_observed_context_transition() -> None:
    simulator = LocalSemanticRankingSimulator(
        {("政治", "CODE", "局长"): 3}
    )
    pipeline = LayeredCandidatePipeline(semantic_ranker=simulator)
    pipeline.set_context(left_text="政治")

    ranked = pipeline.rank(
        [_candidate("县长"), _candidate("局长")],
        {},
    )

    assert [candidate.text for candidate in ranked] == ["局长", "县长"]
    assert ranked[0].semantic_reason == "local-transition:政治"


def test_dynamic_provider_is_a_separate_layer_and_accepts_up_to_seven_chars(
) -> None:
    pipeline = LayeredCandidatePipeline(
        dynamic_providers=[
            lambda _request: [
                {
                    "text": "奥斯特洛夫斯克",
                    "entry_type": "phrase",
                    "pinyin_tone": "ao4 si1 te4 luo4 fu1 si1 ke4",
                    "sort_weight": 10.0,
                    "text_length": 7,
                }
            ]
        ]
    )
    raw = pipeline.collect_dynamic_candidates(
        DynamicCandidateRequest(
            canonical_input="CODE",
            lookup_code="CODE",
            stage="D",
            syllable_count=7,
        )
    )
    records = build_runtime_candidate_records("CODE", raw)
    ranked = rank_runtime_candidates(records, {})

    assert raw[0]["_candidate_source"] == "dynamic-composition"
    assert ranked[0].candidate_layer == "dynamic_composition"
    assert ranked[0].text == "奥斯特洛夫斯克"


def test_user_store_persists_and_exports_local_semantic_transitions(
    tmp_path,
) -> None:
    source = UserLexiconStore(tmp_path / "source.db")
    assert source.record_candidate_transition("政治", "CODE", "局") == 1
    assert source.record_candidate_transition("政治", "CODE", "局") == 2

    payload = source.export_payload()
    target = UserLexiconStore(tmp_path / "target.db")
    target.import_payload(payload)

    assert payload["schema_version"] == 2
    assert target.load_candidate_transition_frequency() == {
        ("政治", "CODE", "局"): 2
    }


def test_decoder_selection_learning_updates_next_context_transition(
    tmp_path,
) -> None:
    decoder = RuntimeDecoderBase.__new__(RuntimeDecoderBase)
    decoder.bmp_to_canonical = {}
    decoder.single_syllable_codes = frozenset({"CODE"})
    decoder.user_lexicon = UserLexiconStore(tmp_path / "user.db")
    decoder._user_freq_by_candidate = {}
    decoder._local_semantic_ranker = LocalSemanticRankingSimulator()
    decoder._candidate_pipeline = LayeredCandidatePipeline(
        semantic_ranker=decoder._local_semantic_ranker
    )
    decoder.set_semantic_context("政治")

    assert decoder.record_selection("CODE", "局") == 1
    assert decoder.user_lexicon.load_candidate_transition_frequency() == {
        ("政治", "CODE", "局"): 1
    }
    assert decoder._candidate_pipeline.context.previous_candidate == "局"


def test_decoder_applies_local_semantic_ranking_without_network(
    tmp_path,
) -> None:
    class FixtureDecoder(RuntimeDecoderBase):
        runtime_source_label = "fixture"

        def _lookup_runtime_candidates_for_decode(
            self,
            canonical,
            plan,
        ):
            return (
                [
                    {
                        "text": "县长",
                        "entry_type": "phrase",
                        "pinyin_tone": "xian4 zhang3",
                        "sort_weight": 100.0,
                        "text_length": 2,
                    },
                    {
                        "text": "局长",
                        "entry_type": "phrase",
                        "pinyin_tone": "ju2 zhang3",
                        "sort_weight": 90.0,
                        "text_length": 2,
                    },
                ],
                plan.lookup_code,
            )

    store = UserLexiconStore(tmp_path / "user.db")
    store.record_candidate_transition("政治", "CODE", "局长")
    decoder = FixtureDecoder.__new__(FixtureDecoder)
    decoder.bmp_to_canonical = {}
    decoder.single_syllable_codes = frozenset({"CODE"})
    decoder.numeric_to_marked_pinyin = {}
    decoder.user_lexicon = store
    decoder._user_freq_by_candidate = {}
    decoder._local_phrase_priority_rules = {}
    decoder._continuous_input_priority_rules = {}
    decoder._char_sort_weight_by_text = {}
    decoder._local_semantic_ranker = LocalSemanticRankingSimulator(
        store.load_candidate_transition_frequency()
    )
    decoder._candidate_pipeline = LayeredCandidatePipeline(
        semantic_ranker=decoder._local_semantic_ranker
    )
    decoder.set_semantic_context("政治")

    _canonical, _active, _pinyin, candidates, _status = decoder.decode_text(
        "CODE"
    )

    assert candidates[:2] == ["局长", "县长"]


def test_one_explicit_selection_outranks_larger_public_sort_weight() -> None:
    high_public = RuntimeCandidateRecord(
        lookup_code="CODE",
        text="安全",
        entry_type="phrase",
        pinyin_tone="an1 quan2",
        sort_weight=1_000_000.0,
        text_length=2,
    )
    selected = RuntimeCandidateRecord(
        lookup_code="CODE",
        text="安权",
        entry_type="phrase",
        pinyin_tone="an1 quan2",
        sort_weight=1.0,
        text_length=2,
    )

    ranked = rank_runtime_candidates(
        [high_public, selected],
        {("CODE", "安权"): 1},
    )

    assert [candidate.text for candidate in ranked] == ["安权", "安全"]


def test_user_frequency_is_scoped_to_exact_lookup_code() -> None:
    first = RuntimeCandidateRecord(
        lookup_code="OTHER",
        text="安权",
        entry_type="phrase",
        pinyin_tone="an1 quan2",
        sort_weight=1.0,
        text_length=2,
    )
    public = RuntimeCandidateRecord(
        lookup_code="OTHER",
        text="安全",
        entry_type="phrase",
        pinyin_tone="an1 quan2",
        sort_weight=100.0,
        text_length=2,
    )

    ranked = rank_runtime_candidates(
        [first, public],
        {("CODE", "安权"): 99},
    )

    assert [candidate.text for candidate in ranked] == ["安全", "安权"]


def test_explicitly_selected_character_can_outrank_public_phrase_prediction() -> None:
    predicted_phrase = RuntimeCandidateRecord(
        lookup_code="CODE",
        text="安全",
        entry_type="phrase",
        pinyin_tone="an1 quan2",
        sort_weight=1_000_000.0,
        text_length=2,
    )
    selected_char = RuntimeCandidateRecord(
        lookup_code="CODE",
        text="安",
        entry_type="char",
        pinyin_tone="an1",
        sort_weight=1.0,
        text_length=1,
    )

    ranked = rank_runtime_candidates(
        [predicted_phrase, selected_char],
        {("CODE", "安"): 1},
    )

    assert [candidate.text for candidate in ranked] == ["安", "安全"]
