from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from syllable.analysis.erhua_surface_classes import (
    apply_surface_class_rules,
    audit_surface_classes,
)


ROOT = Path(__file__).resolve().parents[2]
DRAFT = ROOT / "external_data" / "tmp" / "final_styles_erhua_draft.json"
RULES = ROOT / "external_data" / "tmp" / "erhua_surface_class_rules.json"


def _entries(payload: dict) -> dict[str, dict]:
    return {
        final: entry
        for group in payload["finals"].values()
        for final, entry in group.items()
    }


def test_real_draft_is_closed_under_surface_class_rules() -> None:
    entries = _entries(json.loads(DRAFT.read_text(encoding="utf-8")))
    assert {"v", "ve", "van", "vn"}.isdisjoint(entries)
    audit = audit_surface_classes(DRAFT, RULES)
    assert audit["mismatches"] == []
    assert audit["classes"]["ERHUA-ORAL-AR-A"] == {
        "members": ["a"],
        "surface_ipa": "ää˞ɐ˞",
        "surface_yime": "ää᷊ɐ᷊",
    }
    assert audit["classes"]["ERHUA-ORAL-AR-AI-N"]["members"] == ["ai", "an"]
    assert audit["classes"]["ERHUA-ORAL-IAR"]["members"] == ["ia"]
    assert audit["classes"]["ERHUA-ORAL-UAR-A"]["members"] == ["ua"]
    assert audit["classes"]["ERHUA-ORAL-UAR-AI-N"]["members"] == ["uai", "uan"]
    nasal = audit["classes"]["ERHUA-NASAL-NG"]
    assert nasal["members"] == ["ang", "eng", "iang", "uang", "ueng", "ing", "ong", "iong"]
    assert nasal["surface_ipa"] == "按成员基础主音派生"
    assert nasal["member_surfaces"] == {
        "ang": "ɑɑ̃˞ɑ̃˞",
        "eng": "ɤɤ̃˞ɤ̃˞",
        "iang": "iɑ̃˞ɑ̃˞",
        "uang": "uɑ̃˞ɑ̃˞",
        "ueng": "uɤ̃˞ɤ̃˞",
        "ing": "iɘ̠̆̃˞ɘ̠̆̃˞",
        "ong": "ʊɘ̠̆̃˞ɘ̠̆̃˞",
        "iong": "yɘ̠̆̃˞ɘ̠̆̃˞",
    }


def test_application_preserves_decisions_and_is_idempotent(tmp_path: Path) -> None:
    draft = tmp_path / "draft.json"
    rules = tmp_path / "rules.json"
    shutil.copyfile(DRAFT, draft)
    shutil.copyfile(RULES, rules)
    before = _entries(json.loads(draft.read_text(encoding="utf-8")))
    decisions = {
        final: entry["three_segment_review"]["decision"]
        for final, entry in before.items()
        if "three_segment_review" in entry
    }

    first = apply_surface_class_rules(
        draft,
        rules,
        now=datetime(2026, 8, 11, 14, 0, tzinfo=timezone.utc),
    )
    after = _entries(json.loads(draft.read_text(encoding="utf-8")))
    assert {
        final: entry["three_segment_review"]["decision"]
        for final, entry in after.items()
        if "three_segment_review" in entry
    } == decisions
    assert after["a"]["three_segment_review"]["surface_segments"] != after["ai"]["three_segment_review"]["surface_segments"]
    assert after["ai"]["three_segment_review"]["surface_segments"] == after["an"]["three_segment_review"]["surface_segments"]
    assert after["ua"]["three_segment_review"]["surface_segments"] != after["uai"]["three_segment_review"]["surface_segments"]
    assert after["uai"]["three_segment_review"]["surface_segments"] == after["uan"]["three_segment_review"]["surface_segments"]
    assert {"v", "ve", "van", "vn"}.isdisjoint(after)
    assert audit_surface_classes(draft, rules)["mismatches"] == []

    second = apply_surface_class_rules(
        draft,
        rules,
        now=datetime(2026, 8, 11, 15, 0, tzinfo=timezone.utc),
    )
    assert first["class_count"] == 13
    assert second["changed_members"] == []


def test_metadata_refresh_does_not_increment_manual_revision(tmp_path: Path) -> None:
    draft = tmp_path / "draft.json"
    rules = tmp_path / "rules.json"
    shutil.copyfile(DRAFT, draft)
    shutil.copyfile(RULES, rules)
    payload = json.loads(draft.read_text(encoding="utf-8"))
    entries = _entries(payload)
    review = entries["a"]["three_segment_review"]
    original_revision = review["revision"]
    original_updated = review["updated_utc"]
    review.pop("surface_class", None)
    review.pop("surface_class_rule_version", None)
    entries["a"]["erhua_surface_class"] = {
        "class_id": "OBSOLETE",
        "rule_version": 0,
        "basis": "",
        "technical_alias_of": "",
        "runtime_enabled": False,
    }
    draft.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    result = apply_surface_class_rules(draft, rules)
    after = _entries(json.loads(draft.read_text(encoding="utf-8")))["a"]

    assert "a" in result["metadata_changed_members"]
    assert "a" not in result["surface_changed_members"]
    assert after["three_segment_review"]["revision"] == original_revision
    assert after["three_segment_review"]["updated_utc"] == original_updated
    assert after["erhua_surface_class"]["class_id"] == "ERHUA-ORAL-AR-A"


def test_stale_classification_is_cleared_from_non_member(tmp_path: Path) -> None:
    draft = tmp_path / "draft.json"
    rules = tmp_path / "rules.json"
    shutil.copyfile(DRAFT, draft)
    shutil.copyfile(RULES, rules)
    payload = json.loads(draft.read_text(encoding="utf-8"))
    io = _entries(payload)["io"]
    io["erhua_surface_class"] = {"class_id": "OBSOLETE"}
    io["three_segment_review"]["surface_class"] = "OBSOLETE"
    io["three_segment_review"]["surface_class_rule_version"] = 0
    draft.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    result = apply_surface_class_rules(draft, rules)
    after = _entries(json.loads(draft.read_text(encoding="utf-8")))["io"]

    assert result["stale_classifications_cleared"] == ["io"]
    assert "erhua_surface_class" not in after
    assert "surface_class" not in after["three_segment_review"]
    assert "surface_class_rule_version" not in after["three_segment_review"]
