import csv
import json
from dataclasses import asdict
from pathlib import Path

from yime.utils.syllable_decomposition_audit import (
    build_encoder_failure_rows,
    build_syllable_decomposition_rows,
    build_theoretical_ganyin_omission_rows,
    export_syllable_decomposition_tsv,
    export_syllable_omissions_tsv,
    rule_ids,
)
from syllable.codec.yinjie_encoder import YinjieEncodingError


def test_structured_audit_exposes_normalization_segments_ids_and_rules() -> None:
    rows = build_syllable_decomposition_rows({"a1": "ā", "ya1": "yā", "yu1": "yū"})
    by_pinyin = {row.pinyin_tone: row for row in rows}

    assert by_pinyin["a1"].normalized == "a1"
    assert by_pinyin["a1"].shouyin_label == "'"
    assert by_pinyin["a1"].shouyin_id == "N12"
    assert by_pinyin["a1"].rule_id == "zero-initial"
    assert by_pinyin["ya1"].rule_id == "virtual-j"
    assert by_pinyin["yu1"].rule_id == "virtual-h-rounded"
    assert len(by_pinyin["yu1"].layout_code) == 4
    assert rule_ids(rows) == {"zero-initial", "virtual-j", "virtual-h-rounded"}


def test_export_is_exhaustive_and_keeps_alias_groups(tmp_path: Path) -> None:
    inventory = tmp_path / "inventory.json"
    inventory.write_text('{"a1": "ā", "a5": "a"}', encoding="utf-8")
    output = tmp_path / "audit.tsv"

    assert export_syllable_decomposition_tsv(output, inventory_path=inventory) == 2
    lines = output.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert lines[0].startswith("pinyin_tone\tmarked_pinyin\tnormalized")
    assert all("\tN12\t" in line for line in lines[1:])


def test_checked_in_audit_matches_the_complete_current_encoder_chain() -> None:
    inventory_path = Path("internal_data/pinyin_source_db/lexicon_exports/pinyin_normalized.json")
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    expected = [asdict(row) for row in build_syllable_decomposition_rows(inventory)]
    with Path("internal_data/yime_syllable_decomposition.tsv").open(encoding="utf-8", newline="") as file:
        actual = list(csv.DictReader(file, delimiter="\t"))

    assert actual == expected


def test_theoretical_omissions_explain_rule_and_locked_change_entry() -> None:
    rows = build_theoretical_ganyin_omission_rows({"a1"})
    by_candidate = {row.candidate: row for row in rows}

    assert "a1" not in by_candidate
    assert by_candidate["ue1"].classification == "方案形式与音节拼写/编码形式差异"
    assert by_candidate["ue1"].rule_ids == "ORTH-JQX-UMLAUT"
    assert "不得混入布局改动" in by_candidate["ue1"].lock_scope


def test_encoder_failure_points_to_the_failed_semantic_stage() -> None:
    class FailingEncoder:
        def encode_yinjie_structured(self, _candidate: str) -> None:
            raise YinjieEncodingError("missing ganyin", stage="ganyin_encode")

    rows = build_encoder_failure_rows(
        {"bad1": "bad"},
        encoder=FailingEncoder(),  # type: ignore[arg-type]
    )

    assert len(rows) == 1
    assert rows[0].status == "encoder_failed"
    assert rows[0].source_rule.endswith("ganyin_encoder.py")


def test_checked_in_omission_audit_matches_current_sources() -> None:
    output = Path("internal_data/yime_syllable_omissions.tsv")
    rows = export_syllable_omissions_tsv(output)
    with output.open(encoding="utf-8", newline="") as file:
        actual = list(csv.DictReader(file, delimiter="\t"))

    assert actual == [asdict(row) | {"occurrences": str(row.occurrences)} for row in rows]
    filtered = [row for row in rows if row.status == "filtered_before_inventory"]
    assert [(row.candidate, row.reason) for row in filtered] == [
        ("lan", "reviewed_syllable_scope_exclusion:lan5")
    ]
    assert not any(row.status == "encoder_failed" for row in rows)
