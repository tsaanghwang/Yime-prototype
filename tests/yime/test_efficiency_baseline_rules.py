from tools.generate_efficiency_baseline_report import (
    analyze_syllable_simplification,
    regroup_by_current_shorthand,
    simplify_yime_syllable_code,
    simplify_yime_syllable_code_length,
)


METADATA = {
    "virtual_initial_symbol": "X",
    "ganyin_symbols": {
        "A": {"quality_group": 1, "tone_level": "high"},
        "B": {"quality_group": 1, "tone_level": "mid"},
        "C": {"quality_group": 1, "tone_level": "low"},
    },
}


def test_efficiency_length_preserves_virtual_initial_before_middle_tone_omission() -> None:
    assert simplify_yime_syllable_code("XABC", METADATA) == "XAC"
    assert simplify_yime_syllable_code_length("XABC", METADATA) == 3
    analysis = analyze_syllable_simplification("XABC", METADATA)
    assert analysis["has_virtual_initial"] is True
    assert analysis["omitted_middle_tone"] is True
    assert analysis["saved_keys"] == 1


def test_efficiency_length_merges_adjacent_equal_yinyuan_composing_ganyin() -> None:
    assert simplify_yime_syllable_code_length("XAAA", METADATA) == 2
    analysis = analyze_syllable_simplification("XAAA", METADATA)
    assert analysis["merged_repeat_count"] == 2
    assert analysis["jianpin_length"] == 2


def test_candidate_snapshot_is_regrouped_with_current_shorthand_rules() -> None:
    entry = {"text": "啊", "pinyin_tone": "a1", "yime_code": "legacy"}
    regrouped = regroup_by_current_shorthand(
        {"legacy": [entry]},
        {"a1": "XABC"},
        METADATA,
    )
    assert regrouped == {"XAC": [entry]}
