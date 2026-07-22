from __future__ import annotations

import json
from pathlib import Path

import pytest

from yime.lexicon_bundle.gate import ReadingGate
from yime.lexicon_bundle.syllable_admission import load_syllable_admissions


def _write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _registry(tmp_path: Path, *, scope: str = "all_source_records") -> Path:
    return _write_json(
        tmp_path / "reviews.json",
        {
            "schema_version": "source-syllable-admission-review-v1",
            "reviews": {
                "kuai2": {
                    "status": "approved",
                    "canonical_marked": "kuái",
                    "scope": scope,
                    "rule_id": "SRC-REVIEWED-SYLLABLE-ADMISSION",
                    "decision_basis": "fixture source evidence",
                    "evidence": [{"source": "fixture", "text": "㔞", "reading": "kuái"}],
                }
            },
        },
    )


def test_reviewed_missing_non_neutral_syllable_bridges_inventory(tmp_path: Path) -> None:
    inventory = _write_json(tmp_path / "inventory.json", {"kuai4": "kuài"})
    gate = ReadingGate(inventory, _registry(tmp_path))

    result = gate.admit("㔞", "kuái", codepoint_context=True)

    assert result.accepted
    assert result.numeric == "kuai2"
    assert result.marked == "kuái"
    assert "SRC-REVIEWED-SYLLABLE-ADMISSION" in result.rule_ids


def test_source_attested_neutral_uses_orthographic_rule_without_enumeration(
    tmp_path: Path,
) -> None:
    inventory = _write_json(
        tmp_path / "inventory.json",
        {"qi1": "qī", "qiao1": "qiāo", "lan2": "lán"},
    )
    gate = ReadingGate(inventory, admission_path=None)

    phrase = gate.admit("蹊跷", "qī qiao")
    isolated_source_record = gate.admit("藍", "lan", codepoint_context=True)

    assert phrase.accepted and phrase.numeric == "qi1 qiao5"
    assert isolated_source_record.accepted and isolated_source_record.numeric == "lan5"
    assert "ORTH-SOURCE-ATTESTED-NEUTRAL" in phrase.rule_ids
    assert "ORTH-SOURCE-ATTESTED-NEUTRAL" in isolated_source_record.rule_ids


def test_unreviewed_missing_syllable_remains_rejected(tmp_path: Path) -> None:
    inventory = _write_json(tmp_path / "inventory.json", {"kuai4": "kuài"})
    gate = ReadingGate(inventory, admission_path=None)
    result = gate.admit("㔞", "kuái", codepoint_context=True)
    assert not result.accepted
    assert result.reason == "outside_current_decoder_inventory:kuai2"


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
