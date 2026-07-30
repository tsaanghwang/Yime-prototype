from __future__ import annotations

from pathlib import Path

from yime.input_method.core.char_code_index import CharCodeCandidate
from yime.input_method.core.layered_candidate_pipeline import (
    LayeredCandidatePipeline,
)
from yime.input_method.core.runtime_decoder_base import RuntimeDecoderBase
from yime.input_method.core.runtime_ranking import annotate_candidate_source
from yime.input_method.utils.user_lexicon import UserLexiconStore
from yime.utils.code_modes import YimeCodeMode


PINYIN_TO_CODE = {
    "jia3": "A",
    "yi3": "B",
}


class _LearningDecoder(RuntimeDecoderBase):
    runtime_source_label = "fixture"

    def __init__(self, user_db_path: Path) -> None:
        self.bmp_to_canonical = {}
        self.code_mode = YimeCodeMode.VARIABLE
        self.pinyin_to_code_by_mode = {
            YimeCodeMode.FULL: dict(PINYIN_TO_CODE),
            YimeCodeMode.VARIABLE: dict(PINYIN_TO_CODE),
            YimeCodeMode.SHORTHAND: dict(PINYIN_TO_CODE),
        }
        self.pinyin_to_canonical = dict(PINYIN_TO_CODE)
        self.single_syllable_codes = frozenset(PINYIN_TO_CODE.values())
        self.numeric_to_marked_pinyin = {
            "jia3": "jiǎ",
            "yi3": "yǐ",
        }
        self.user_lexicon = UserLexiconStore(user_db_path)
        self._local_phrase_priority_rules = {}
        self._continuous_input_priority_rules = {}
        self._char_sort_weight_by_text = {
            "甲": 300.0,
            "乙": 200.0,
        }
        self._candidate_pipeline = LayeredCandidatePipeline()
        self._last_ranked_candidates_by_text = {}
        self._pending_sentence_selections = []
        self._install_builtin_dynamic_candidate_providers()
        self.reload_user_lexicon()

    def get_char_candidates(self, code):
        return {
            "A": [
                CharCodeCandidate(
                    "甲",
                    "A",
                    pinyin_tone="jia3",
                    sort_weight=300.0,
                    is_common=True,
                )
            ],
            "B": [
                CharCodeCandidate(
                    "乙",
                    "B",
                    pinyin_tone="yi3",
                    sort_weight=200.0,
                    is_common=True,
                )
            ],
        }.get(code, [])

    def _lookup_runtime_candidates_for_decode(self, canonical, plan):
        raw = [
            {
                "text": candidate.text,
                "entry_type": "char",
                "pinyin_tone": candidate.pinyin_tone,
                "sort_weight": candidate.sort_weight,
                "is_common": candidate.is_common,
                "text_length": 1,
            }
            for candidate in self.get_char_candidates(plan.lookup_code)
        ]
        raw.extend(self._user_overlays.get(plan.lookup_code, []))
        return raw, plan.lookup_code

    def reload_user_lexicon(self) -> None:
        self._user_freq_by_candidate = (
            self.user_lexicon.load_candidate_frequency()
        )
        loaded = self.user_lexicon.load_phrase_candidates(
            self.pinyin_to_canonical
        )
        self._user_overlays = {
            code: [
                annotate_candidate_source(candidate, "overlay")
                for candidate in candidates
            ]
            for code, candidates in loaded.items()
        }


def test_selected_character_sequence_is_learned_as_whole_sentence(
    tmp_path: Path,
) -> None:
    user_db = tmp_path / "user.db"
    decoder = _LearningDecoder(user_db)

    assert decoder.decode_text("A")[3] == ["甲"]
    decoder.record_selection("A", "甲")
    assert decoder.decode_text("B")[3] == ["乙"]
    decoder.record_selection("B", "乙")

    assert decoder.record_sentence_commit("甲乙") is True
    detail = decoder.user_lexicon.list_phrase_entries(term="甲乙")[0]
    assert detail.numeric_pinyin == "jia3 yi3"
    assert detail.marked_pinyin == "jiǎ yǐ"
    assert detail.source_note == "auto_learned_committed_sentence"

    restarted = _LearningDecoder(user_db)
    assert restarted.decode_text("AB")[3][0] == "甲乙"
    assert (
        restarted._last_ranked_candidates_by_text["甲乙"].candidate_layer
        == "user_learning"
    )


def test_edited_commit_does_not_turn_unverified_text_into_user_phrase(
    tmp_path: Path,
) -> None:
    decoder = _LearningDecoder(tmp_path / "user.db")
    decoder.decode_text("A")
    decoder.record_selection("A", "甲")
    decoder.decode_text("B")
    decoder.record_selection("B", "乙")

    assert decoder.record_sentence_commit("甲丙") is False
    assert decoder.user_lexicon.list_phrase_entries(term="甲丙") == []


def test_commit_clears_pending_selection_trace_even_when_learning_rejected(
    tmp_path: Path,
) -> None:
    decoder = _LearningDecoder(tmp_path / "user.db")
    decoder.decode_text("A")
    decoder.record_selection("A", "甲")

    assert decoder.record_sentence_commit("手工改写") is False
    assert decoder.record_sentence_commit("甲") is False


class _ProverbLearningDecoder(_LearningDecoder):
    _PINYIN_TO_CODE = {
        "mo2": "M",
        "gao1": "G",
        "yi1": "Y",
        "chi3": "C",
        "dao4": "D",
        "zhang4": "Z",
    }
    _SEGMENTS = {
        "MG": [
            ("魔髙", "mo2 gao1", 200.0),
            ("魔高", "mo2 gao1", 100.0),
        ],
        "YC": [("一尺", "yi1 chi3", 100.0)],
        "DG": [("道高", "dao4 gao1", 100.0)],
        "YZ": [("一丈", "yi1 zhang4", 100.0)],
    }

    def __init__(self, user_db_path: Path) -> None:
        self.bmp_to_canonical = {}
        self.code_mode = YimeCodeMode.VARIABLE
        self.pinyin_to_code_by_mode = {
            mode: dict(self._PINYIN_TO_CODE)
            for mode in YimeCodeMode
        }
        self.pinyin_to_canonical = dict(self._PINYIN_TO_CODE)
        self.single_syllable_codes = frozenset(
            self._PINYIN_TO_CODE.values()
        )
        self.numeric_to_marked_pinyin = {}
        self.user_lexicon = UserLexiconStore(user_db_path)
        self._local_phrase_priority_rules = {}
        self._continuous_input_priority_rules = {}
        self._char_sort_weight_by_text = {}
        self._candidate_pipeline = LayeredCandidatePipeline()
        self._last_ranked_candidates_by_text = {}
        self._pending_sentence_selections = []
        self.reload_user_lexicon()

    def _lookup_runtime_candidates_for_decode(self, canonical, plan):
        raw = [
            {
                "text": text,
                "entry_type": "phrase",
                "pinyin_tone": pinyin,
                "sort_weight": weight,
                "text_length": len(text),
            }
            for text, pinyin, weight in self._SEGMENTS.get(
                plan.lookup_code,
                [],
            )
        ]
        raw.extend(self._user_overlays.get(plan.lookup_code, []))
        return raw, plan.lookup_code


def test_segmented_proverb_is_learned_and_directly_available_next_time(
    tmp_path: Path,
) -> None:
    user_db = tmp_path / "user.db"
    decoder = _ProverbLearningDecoder(user_db)
    selections = [
        ("MG", "魔高"),
        ("YC", "一尺"),
        ("DG", "道高"),
        ("YZ", "一丈"),
    ]
    target = "".join(text for _code, text in selections)

    for code, text in selections:
        assert text in decoder.decode_text(code)[3]
        decoder.record_selection(code, text)

    assert decoder.record_sentence_commit(target) is True
    full_code = "".join(code for code, _text in selections)
    assert decoder.decode_text(full_code)[3][0] == target

    restarted = _ProverbLearningDecoder(user_db)
    assert restarted.decode_text(full_code)[3][0] == target


def test_gao_selection_weight_is_not_recorded_for_lookalike_gao(
    tmp_path: Path,
) -> None:
    decoder = _ProverbLearningDecoder(tmp_path / "user.db")

    assert decoder.decode_text("MG")[3][:2] == ["魔髙", "魔高"]
    assert decoder.record_selection("MG", "魔高") == 1
    assert decoder.decode_text("MG")[3][0] == "魔高"
    assert decoder._user_freq_by_candidate[("MG", "魔高")] == 1
    assert ("MG", "魔髙") not in decoder._user_freq_by_candidate
