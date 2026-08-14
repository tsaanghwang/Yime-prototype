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
    assert audit["classes"]["ERHUA-ORAL-AR"] == {
        "members": ["a", "ai", "an"],
        "surface_ipa": "ää˞ä˞",
        "surface_yime": "ää᷊ä᷊",
    }
    assert audit["classes"]["ERHUA-ORAL-IAR"]["members"] == ["ia"]
    assert audit["classes"]["ERHUA-ORAL-UAR"]["members"] == ["ua", "uai", "uan"]


def test_application_preserves_decisions_and_is_idempotent(tmp_path: Path) -> None:
    draft = tmp_path / "draft.json"
    rules = tmp_path / "rules.json"
    shutil.copyfile(DRAFT, draft)
    shutil.copyfile(RULES, rules)
    before = _entries(json.loads(draft.read_text(encoding="utf-8")))
    decisions = {
        final: entry["three_segment_review"]["decision"]
        for final, entry in before.items()
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
    } == decisions
    assert after["a"]["three_segment_review"]["surface_segments"] == after["ai"]["three_segment_review"]["surface_segments"]
    assert after["ai"]["three_segment_review"]["surface_segments"] == after["an"]["three_segment_review"]["surface_segments"]
    assert {"v", "ve", "van", "vn"}.isdisjoint(after)
    assert audit_surface_classes(draft, rules)["mismatches"] == []

    second = apply_surface_class_rules(
        draft,
        rules,
        now=datetime(2026, 8, 11, 15, 0, tzinfo=timezone.utc),
    )
    assert first["class_count"] == 9
    assert second["changed_members"] == []
