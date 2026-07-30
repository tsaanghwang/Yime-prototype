from __future__ import annotations

from yime.input_method.core.char_code_index import CharCodeCandidate
from yime.input_method.core.layered_candidate_pipeline import (
    DynamicCandidateRequest,
    LayeredCandidatePipeline,
)
from yime.input_method.core.neutral_tone_fallback import (
    NeutralToneFallbackProvider,
)
from yime.input_method.core.runtime_decoder_base import RuntimeDecoderBase


PINYIN_TO_CODE = {
    "qi3": "QI",
    "lai2": "LAI2",
    "lai5": "LAI5",
    "hm5": "HM5",
}


def _candidate(
    text: str,
    code: str,
    pinyin_tone: str,
    weight: float,
) -> CharCodeCandidate:
    return CharCodeCandidate(
        text=text,
        code=code,
        pinyin_tone=pinyin_tone,
        sort_weight=weight,
        is_common=True,
    )


def _provider(
    candidates_by_code: dict[str, list[CharCodeCandidate]],
) -> NeutralToneFallbackProvider:
    return NeutralToneFallbackProvider(
        get_pinyin_to_code=lambda: PINYIN_TO_CODE,
        get_char_candidates=lambda code: candidates_by_code.get(code, []),
    )


def _request(
    lookup_code: str = "QILAI5",
    *,
    stage: str = "D",
    syllable_count: int = 2,
) -> DynamicCandidateRequest:
    return DynamicCandidateRequest(
        canonical_input=lookup_code,
        lookup_code=lookup_code,
        stage=stage,
        syllable_count=syllable_count,
    )


def test_missing_neutral_char_reading_falls_back_to_same_base_reading() -> None:
    provider = _provider(
        {
            "QI": [_candidate("起", "QI", "qi3", 100.0)],
            "LAI2": [_candidate("来", "LAI2", "lai2", 90.0)],
        }
    )

    candidates = provider(_request())

    assert [candidate["text"] for candidate in candidates] == ["起来"]
    assert candidates[0]["pinyin_tone"] == "qi3 lai5"
    assert candidates[0]["_neutral_tone_fallback_count"] == 1


def test_fallback_is_ephemeral_and_does_not_create_neutral_char_candidate() -> None:
    base_candidate = _candidate("来", "LAI2", "lai2", 90.0)
    candidates_by_code = {
        "QI": [_candidate("起", "QI", "qi3", 100.0)],
        "LAI2": [base_candidate],
    }
    provider = _provider(candidates_by_code)

    provider(_request())

    assert candidates_by_code["LAI2"] == [base_candidate]
    assert "LAI5" not in candidates_by_code


def test_single_syllable_and_incomplete_input_do_not_use_phrase_fallback() -> None:
    provider = _provider(
        {"LAI2": [_candidate("来", "LAI2", "lai2", 90.0)]}
    )

    assert provider(_request("LAI5", stage="B", syllable_count=1)) == []
    assert provider(_request("QILAI", stage="C", syllable_count=1)) == []


def test_reviewed_special_neutral_without_base_tone_is_not_invented() -> None:
    provider = _provider(
        {"QI": [_candidate("起", "QI", "qi3", 100.0)]}
    )

    assert provider(_request("QIHM5")) == []


def test_unregistered_neutral_form_cannot_trigger_fallback() -> None:
    provider = _provider(
        {
            "QI": [_candidate("起", "QI", "qi3", 100.0)],
            "LAI2": [_candidate("来", "LAI2", "lai2", 90.0)],
        }
    )

    assert provider(_request("QIUNKNOWN")) == []


def test_exact_neutral_candidate_remains_available_beside_fallback() -> None:
    provider = _provider(
        {
            "QI": [_candidate("起", "QI", "qi3", 100.0)],
            "LAI5": [_candidate("俫", "LAI5", "lai5", 80.0)],
            "LAI2": [_candidate("来", "LAI2", "lai2", 90.0)],
        }
    )

    texts = [candidate["text"] for candidate in provider(_request())]

    assert "起来" in texts
    assert "起俫" not in texts


def test_runtime_decoder_returns_fallback_when_exact_phrase_is_absent() -> None:
    class FixtureDecoder(RuntimeDecoderBase):
        runtime_source_label = "fixture"

        def _lookup_runtime_candidates_for_decode(self, canonical, plan):
            return [], plan.lookup_code

        def get_char_candidates(self, code):
            return {
                "QI": [_candidate("起", "QI", "qi3", 100.0)],
                "LAI2": [_candidate("来", "LAI2", "lai2", 90.0)],
            }.get(code, [])

    decoder = FixtureDecoder.__new__(FixtureDecoder)
    decoder.bmp_to_canonical = {}
    decoder.pinyin_to_canonical = dict(PINYIN_TO_CODE)
    decoder.single_syllable_codes = frozenset(PINYIN_TO_CODE.values())
    decoder.numeric_to_marked_pinyin = {}
    decoder._user_freq_by_candidate = {}
    decoder._local_phrase_priority_rules = {}
    decoder._continuous_input_priority_rules = {}
    decoder._char_sort_weight_by_text = {}
    decoder._candidate_pipeline = LayeredCandidatePipeline()
    decoder._install_builtin_dynamic_candidate_providers()

    _canonical, _active, _pinyin, candidates, _status = decoder.decode_text(
        "QILAI5"
    )

    assert candidates[0] == "起来"
