from __future__ import annotations

from yime.input_method.core.bounded_character_composition import (
    BoundedCharacterCompositionProvider,
)
from yime.input_method.core.char_code_index import CharCodeCandidate
from yime.input_method.core.layered_candidate_pipeline import (
    DynamicCandidateRequest,
    LayeredCandidatePipeline,
)


def _char(
    text: str,
    code: str,
    pinyin: str,
    weight: float,
    *,
    common: bool = True,
) -> CharCodeCandidate:
    return CharCodeCandidate(
        text=text,
        code=code,
        pinyin_tone=pinyin,
        sort_weight=weight,
        is_common=common,
    )


def test_beam_composition_keeps_high_weight_path_without_cartesian_product() -> None:
    mapping = {"jia3": "A", "yi3": "B", "bing3": "C"}
    chars = {
        "A": [
            _char("甲", "A", "jia3", 300.0),
            _char("假", "A", "jia3", 100.0),
        ],
        "B": [
            _char("乙", "B", "yi3", 300.0),
            _char("已", "B", "yi3", 100.0),
        ],
        "C": [
            _char("丙", "C", "bing3", 300.0),
            _char("炳", "C", "bing3", 100.0),
        ],
    }
    provider = BoundedCharacterCompositionProvider(
        get_pinyin_to_code=lambda: mapping,
        get_char_candidates=lambda code: chars.get(code, []),
        beam_width=3,
        result_limit=3,
    )

    candidates = provider(
        DynamicCandidateRequest("ABC", "ABC", "D", 3)
    )

    assert len(candidates) == 3
    assert candidates[0]["text"] == "甲乙丙"
    assert candidates[0]["_composition_components"] == [
        "甲/jia3",
        "乙/yi3",
        "丙/bing3",
    ]


def test_global_pruner_deduplicates_rejects_invalid_and_limits_head_cluster() -> None:
    def provider_one(_request):
        return [
            {
                "text": "甲乙",
                "pinyin_tone": "jia3 yi3",
                "sort_weight": 10.0,
                "text_length": 2,
                "is_common": True,
                "_composition_score": 10.0,
            },
            {
                "text": "甲丙",
                "pinyin_tone": "jia3 bing3",
                "sort_weight": 9.0,
                "text_length": 2,
                "is_common": True,
                "_composition_score": 9.0,
            },
            {
                "text": "错误长度",
                "pinyin_tone": "cuo4",
                "sort_weight": 999.0,
                "text_length": 4,
                "is_common": True,
            },
        ]

    def provider_two(_request):
        return [
            {
                "text": "甲乙",
                "pinyin_tone": "jia3 yi3",
                "sort_weight": 1.0,
                "text_length": 2,
                "is_common": True,
                "_composition_score": 1.0,
            },
            {
                "text": "乙甲",
                "pinyin_tone": "yi3 jia3",
                "sort_weight": 8.0,
                "text_length": 2,
                "is_common": True,
                "_composition_score": 8.0,
            },
        ]

    pipeline = LayeredCandidatePipeline(
        dynamic_providers=[provider_one, provider_two],
        dynamic_candidate_limit=3,
        dynamic_per_leading_char_limit=1,
    )

    candidates = pipeline.collect_dynamic_candidates(
        DynamicCandidateRequest("AB", "AB", "D", 2)
    )

    assert [candidate["text"] for candidate in candidates] == [
        "甲乙",
        "乙甲",
    ]
    assert candidates[0]["sort_weight"] == 10.0
