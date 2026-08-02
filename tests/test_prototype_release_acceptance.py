from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "run_prototype_release_acceptance.py"
POLICY = ROOT / "internal_data" / "prototype_release_acceptance_policy.json"


def _load_runner():
    spec = importlib.util.spec_from_file_location("prototype_release_acceptance", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_acceptance_policy_keeps_external_handoff_out_of_scope() -> None:
    payload = json.loads(POLICY.read_text(encoding="utf-8"))

    assert payload["safeguards"] == {
        "canonical_generated_files_mutated": False,
        "existing_gates_removed": False,
        "restart_allowed": False,
        "windows_yime_export_allowed": False,
    }
    assert "prepare_windows_yime_lexicon.ps1" in payload["forbidden_entrypoints"]
    for document, anchors in payload["documentation_anchors"].items():
        text = (ROOT / document).read_text(encoding="utf-8")
        assert all(anchor in text for anchor in anchors)


def test_acceptance_runner_rejects_forbidden_or_restart_commands() -> None:
    runner = _load_runner()
    forbidden = {"prepare_windows_yime_lexicon.ps1"}

    runner._assert_safe_command(["python", "tools/build_lexicon_source_bundle.py"], forbidden)
    with pytest.raises(ValueError, match="forbidden external handoff"):
        runner._assert_safe_command(
            ["powershell", "tools/prepare_windows_yime_lexicon.ps1"], forbidden
        )
    with pytest.raises(ValueError, match="restart-capable"):
        runner._assert_safe_command(["Restart-Computer"], forbidden)

def test_materialized_inventory_entrypoint_loads_from_repository_root() -> None:
    completed = subprocess.run(
        [sys.executable, "tools/refresh_materialized_syllable_inventory.py", "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "--db-path" in completed.stdout