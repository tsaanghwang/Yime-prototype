from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "internal_data" / "archived_entrypoints.json"


def test_archived_entrypoints_are_explicit_and_non_destructive() -> None:
    payload = json.loads(CATALOG.read_text(encoding="utf-8"))

    assert payload["archive_strategy"] == "retain_in_place_to_preserve_consumers"
    assert payload["safeguards"] == {
        "compatibility_paths_preserved": True,
        "existing_gates_removed": False,
        "files_moved": False,
        "windows_yime_touched": False,
    }
    entries = payload["entries"]
    assert len(entries) == len({entry["path"] for entry in entries})
    assert all(entry["prototype_acceptance"] is False for entry in entries)
    for entry in entries:
        assert (ROOT / entry["path"]).is_file(), entry["path"]
        assert (ROOT / entry["replacement"]).is_file(), entry["replacement"]