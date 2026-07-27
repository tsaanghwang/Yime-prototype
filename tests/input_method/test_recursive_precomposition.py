from __future__ import annotations

from yime.input_method.core.layered_candidate_pipeline import (
    DynamicCandidateRequest,
    LayeredCandidatePipeline,
)
from yime.input_method.core.recursive_precomposition import (
    RecursivePrecompositionProvider,
)


def _candidate(
    text: str,
    pinyin: str,
    weight: float,
    *,
    atom: bool = False,
) -> dict[str, object]:
    return {
        "text": text,
        "pinyin_tone": pinyin,
        "sort_weight": weight,
        "is_common": True,
        "entry_type": (
            "precomposition_atom" if atom else "phrase"
        ),
        "_precomposition_atom": atom,
    }


def _provider(
    components: dict[tuple[str, int], list[dict[str, object]]],
) -> RecursivePrecompositionProvider:
    mapping = {
        f"s{index + 1}": code
        for index, code in enumerate("ABCDEFGHIJKL")
    }
    return RecursivePrecompositionProvider(
        get_pinyin_to_code=lambda: mapping,
        get_component_candidates=lambda code, width: components.get(
            (code, width),
            [],
        ),
        chart_beam_width=64,
        result_limit=32,
    )


def test_recursive_precomposition_reuses_partial_results() -> None:
    provider = _provider(
        {
            ("AB", 2): [_candidate("国土", "s1 s2", 100)],
            ("CDE", 3): [_candidate("资源部", "s3 s4 s5", 100)],
            ("FGH", 3): [_candidate("管理局", "s6 s7 s8", 100)],
        }
    )

    candidates = provider(
        DynamicCandidateRequest("ABCDEFGH", "ABCDEFGH", "D", 8)
    )

    assert candidates[0]["text"] == "国土资源部管理局"
    assert candidates[0]["_composition_components"] == [
        "国土/s1 s2",
        "资源部/s3 s4 s5",
        "管理局/s6 s7 s8",
    ]
    assert candidates[0]["_precomposition_rounds"] == 2


def test_long_precomposition_atom_can_cross_four_syllable_boundary() -> None:
    provider = _provider(
        {
            ("ABCDE", 5): [
                _candidate(
                    "阿尔及利亚",
                    "s1 s2 s3 s4 s5",
                    100,
                    atom=True,
                )
            ],
            ("FG", 2): [_candidate("代表", "s6 s7", 100)],
        }
    )

    candidates = provider(
        DynamicCandidateRequest("ABCDEFG", "ABCDEFG", "D", 7)
    )

    assert candidates[0]["text"] == "阿尔及利亚代表"
    assert candidates[0]["_precomposition_atom_count"] == 1


def test_unmarked_long_candidate_is_not_an_atomic_shortcut() -> None:
    provider = _provider(
        {
            ("ABCDE", 5): [
                _candidate(
                    "民主集中制",
                    "s1 s2 s3 s4 s5",
                    100,
                )
            ]
        }
    )

    assert (
        provider(
            DynamicCandidateRequest("ABCDE", "ABCDE", "D", 5)
        )
        == []
    )


def test_layered_pruner_accepts_recursive_candidates_up_to_twelve() -> None:
    provider = _provider(
        {
            ("ABCD", 4): [_candidate("甲乙丙丁", "s1 s2 s3 s4", 100)],
            ("EFGH", 4): [_candidate("戊己庚辛", "s5 s6 s7 s8", 100)],
            ("IJKL", 4): [
                _candidate("壬癸子丑", "s9 s10 s11 s12", 100)
            ],
        }
    )
    pipeline = LayeredCandidatePipeline(
        dynamic_providers=[provider],
    )

    candidates = pipeline.collect_dynamic_candidates(
        DynamicCandidateRequest(
            "ABCDEFGHIJKL",
            "ABCDEFGHIJKL",
            "D",
            12,
        )
    )

    assert [candidate["text"] for candidate in candidates] == [
        "甲乙丙丁戊己庚辛壬癸子丑"
    ]
