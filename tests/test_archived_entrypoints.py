from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "internal_data" / "archived_entrypoints.json"


def test_archived_entrypoints_are_explicit_and_non_destructive() -> None:
    payload = json.loads(CATALOG.read_text(encoding="utf-8"))

    assert payload["archive_strategy"] == "retain_in_place_to_preserve_consumers"
    assert payload["product_repository"] == r"C:\dev\Yime"
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

    blocked = {
        entry["path"]
        for entry in entries
        if entry["state"] == "blocked_detached_product_workflow"
    }
    assert {
        "scripts/build_portable_release.bat",
        "scripts/build_setup_release.bat",
        "scripts/build_friend_trial_package.bat",
        "tools/prepare_windows_yime_lexicon.ps1",
        "tools/prepare_windows_yime_auxiliary_assets.py",
        "tools/verify_default_runtime_handoff.py",
        "tools/run_msklc_packaging_pipeline.py",
        "tools/run_msklc_install_pipeline.py",
        "tools/reset_msklc_install_state.py",
        "tools/verify_seed_install_flow.py",
        "tools/export_and_deploy_weasel_yime.ps1",
        ".github/workflows/release.yml",
        "yime_portable.spec",
        "yime_setup.iss",
    } <= blocked
