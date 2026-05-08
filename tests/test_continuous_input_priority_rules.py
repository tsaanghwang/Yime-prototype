from __future__ import annotations

from yime.input_method.core.char_code_index import CharCodeIndex
from yime.input_method.core.decoders import RuntimeCandidateDecoder


def _build_runtime_decoder() -> RuntimeCandidateDecoder:
    runtime_decoder = RuntimeCandidateDecoder.__new__(RuntimeCandidateDecoder)
    runtime_decoder.bmp_to_canonical = {}
    runtime_decoder.numeric_to_marked_pinyin = {}
    runtime_decoder._user_freq_by_candidate = {}
    runtime_decoder._local_phrase_priority_rules = {}
    runtime_decoder._continuous_input_priority_rules = {}
    runtime_decoder.by_code = {}
    runtime_decoder._char_sort_weight_by_text = {}
    runtime_decoder._phrase_prefix_index = {}
    runtime_decoder.char_code_index = CharCodeIndex.from_runtime_candidates(runtime_decoder.by_code)
    return runtime_decoder


def test_continuous_input_context_rule_promotes_partial_phrase() -> None:
    runtime_decoder = _build_runtime_decoder()
    runtime_decoder._continuous_input_priority_rules = {
        "abcdxy": {
            "你好啊": 500.0,
        }
    }
    runtime_decoder._phrase_prefix_index = {
        "abcdxy": [
            {
                "text": "你好吗",
                "entry_type": "phrase",
                "pinyin_tone": "ni3 hao3 ma5",
                "yime_code": "abcdxyzz",
                "sort_weight": 320.0,
                "text_length": 3,
                "is_common": 1,
            },
            {
                "text": "你好啊",
                "entry_type": "phrase",
                "pinyin_tone": "ni3 hao3 a5",
                "yime_code": "abcdxywv",
                "sort_weight": 280.0,
                "text_length": 3,
                "is_common": 1,
            },
        ]
    }

    canonical, active, _pinyin, candidates, status = runtime_decoder.decode_text("abcdxy")

    assert canonical == "abcdxy"
    assert active == "abcd"
    assert candidates[:2] == ["你好啊", "你好吗"]
    assert "已完成 1 个音节" in status


def test_continuous_input_context_rule_promotes_exact_multisyllable_phrase() -> None:
    runtime_decoder = _build_runtime_decoder()
    runtime_decoder._continuous_input_priority_rules = {
        "abcdefgh": {
            "你好": 500.0,
        }
    }
    runtime_decoder.by_code = {
        "abcdefgh": [
            {
                "text": "你号",
                "entry_type": "phrase",
                "pinyin_tone": "ni3 hao4",
                "yime_code": "abcdefgh",
                "sort_weight": 320.0,
                "text_length": 2,
                "is_common": 1,
            },
            {
                "text": "你好",
                "entry_type": "phrase",
                "pinyin_tone": "ni3 hao3",
                "yime_code": "abcdefgh",
                "sort_weight": 280.0,
                "text_length": 2,
                "is_common": 1,
            },
        ]
    }
    runtime_decoder.char_code_index = CharCodeIndex.from_runtime_candidates(runtime_decoder.by_code)

    canonical, active, _pinyin, candidates, status = runtime_decoder.decode_text("abcdefgh")

    assert canonical == "abcdefgh"
    assert active == "abcdefgh"
    assert candidates[:2] == ["你好", "你号"]
    assert "音节" in status
