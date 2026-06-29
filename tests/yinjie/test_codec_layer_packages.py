import unittest

from syllable.codec.input_shorthand import omit_middle_tone_if_same_quality_run
from syllable.codec.model_full_code import Yinjie as LayerYinjie
from syllable.codec.variable_length_yinyuan import (
    merge_adjacent_duplicate_symbols,
    simplify_ganyin_repeats,
    split_loose_encoded_string,
)
from syllable.codec.yinjie import Yinjie as LegacyYinjie


class TestCodecLayerPackages(unittest.TestCase):
    def test_model_full_code_exports_legacy_yinjie_type(self):
        self.assertIs(LayerYinjie, LegacyYinjie)

    def test_variable_length_yinyuan_merges_adjacent_duplicates(self):
        merged, merged_repeat_count = merge_adjacent_duplicate_symbols(["A", "B", "B", "C"])
        self.assertEqual(merged, ["A", "B", "C"])
        self.assertEqual(merged_repeat_count, 1)

    def test_variable_length_yinyuan_keeps_simplify_behavior(self):
        self.assertEqual(simplify_ganyin_repeats("ABBC"), "ABC")

    def test_variable_length_yinyuan_loose_split_returns_yinjie(self):
        self.assertIsInstance(split_loose_encoded_string("ABC"), LegacyYinjie)

    def test_input_shorthand_omits_middle_tone_for_same_quality_run(self):
        metadata = {
            "A": {"quality_group": 1, "tone_level": "high"},
            "B": {"quality_group": 1, "tone_level": "mid"},
            "C": {"quality_group": 1, "tone_level": "low"},
        }
        compressed, omitted = omit_middle_tone_if_same_quality_run(["A", "B", "C"], metadata)
        self.assertEqual(compressed, ["A", "C"])
        self.assertTrue(omitted)


if __name__ == "__main__":
    unittest.main()
