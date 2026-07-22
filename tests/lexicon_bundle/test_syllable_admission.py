from __future__ import annotations

import json
from pathlib import Path

import pytest

from yime.lexicon_bundle.gate import ReadingGate
from yime.lexicon_bundle.syllable_admission import load_syllable_admissions


def _write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _registry(tmp_path: Path, *, scope: str = "multi_character_only") -> Path:
    return _write_json(
        tmp_path / "reviews.json",
        {
            "schema_version": "source-syllable-admission-review-v1",
            "reviews": {
                "qiao5": {
                    "status": "approved",
                    "canonical_marked": "qiao",
                    "scope": scope,
                    "rule_id": "SRC-REVIEWED-SYLLABLE-ADMISSION",
                    "decision_basis": "fixture source evidence",
                    "evidence": [{"source": "fixture", "text": "蹊跷", "reading": "qī qiao"}],
                }
            },
        },
    )


def test_reviewed_missing_syllable_bridges_inventory_for_phrase_only(tmp_path: Path) -> None:
    inventory = _write_json(tmp_path / "inventory.json", {"qi1": "qī"})
    gate = ReadingGate(inventory, _registry(tmp_path))

    result = gate.admit("蹊跷", "qī qiao")

    assert result.accepted
    assert result.numeric == "qi1 qiao5"
    assert result.marked == "qī qiao"
    assert "SRC-REVIEWED-SYLLABLE-ADMISSION" in result.rule_ids
    assert not gate.admit("跷", "qiao").accepted

    inventory_with_reviewed = _write_json(
        tmp_path / "rebuilt_inventory.json", {"qi1": "qī", "qiao5": "qiao"}
    )
    rebuilt_gate = ReadingGate(inventory_with_reviewed, _registry(tmp_path))
    excluded = rebuilt_gate.admit("跷", "qiao")
    assert not excluded.accepted
    assert excluded.reason == "reviewed_syllable_scope_exclusion:qiao5"


def test_unreviewed_missing_syllable_remains_rejected(tmp_path: Path) -> None:
    inventory = _write_json(tmp_path / "inventory.json", {"qi1": "qī"})
    gate = ReadingGate(inventory, admission_path=None)
    result = gate.admit("蹊跷", "qī qiao")
    assert not result.accepted
    assert result.reason == "outside_current_decoder_inventory:qiao5"


def test_registry_cannot_approve_unadmitted_spelling(tmp_path: Path) -> None:
    path = _write_json(
        tmp_path / "reviews.json",
        {
            "schema_version": "source-syllable-admission-review-v1",
            "reviews": {
                "fi4": {
                    "status": "approved",
                    "canonical_marked": "fì",
                    "scope": "all_source_records",
                    "evidence": [{"source": "fixture"}],
                }
            },
        },
    )
    with pytest.raises(ValueError, match="does not canonicalize"):
        load_syllable_admissions(path)
