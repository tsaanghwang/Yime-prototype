from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "internal_data" / "prototype_smoke_scenarios.json"


def test_prototype_smoke_manifest_is_safe_and_complete() -> None:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert payload["constraints"] == {
        "gui_automation": False,
        "real_user_directory_allowed": False,
        "restart_allowed": False,
        "windows_yime_export_allowed": False,
    }
    scenarios = {scenario["id"]: scenario for scenario in payload["scenarios"]}
    assert set(scenarios) == {
        "backspace",
        "candidate_pagination",
        "combination_input",
        "cross_window_paste",
        "focus_restore",
        "mode_switch",
    }
    for scenario in scenarios.values():
        assert scenario["tests"]
        for nodeid in scenario["tests"]:
            relative_path = nodeid.split("::", 1)[0]
            assert (ROOT / relative_path).is_file(), nodeid