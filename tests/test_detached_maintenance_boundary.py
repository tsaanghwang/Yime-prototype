from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PRODUCT_REPOSITORY = r"C:\dev\Yime"


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


@pytest.mark.parametrize(
    "entrypoint",
    [
        "tools/prepare_windows_yime_auxiliary_assets.py",
        "tools/verify_default_runtime_handoff.py",
        "tools/run_msklc_packaging_pipeline.py",
        "tools/run_msklc_install_pipeline.py",
        "tools/reset_msklc_install_state.py",
        "tools/verify_seed_install_flow.py",
    ],
)
def test_obsolete_python_entrypoints_reject_before_work(
    entrypoint: str,
) -> None:
    completed = _run([sys.executable, entrypoint, "--help"])

    assert completed.returncode == 2
    assert "Obsolete workflow blocked" in completed.stderr
    assert PRODUCT_REPOSITORY in completed.stderr


@pytest.mark.skipif(sys.platform != "win32", reason="Windows command entrypoints")
@pytest.mark.parametrize(
    "entrypoint",
    [
        "scripts/build_portable_release.bat",
        "scripts/build_setup_release.bat",
        "scripts/build_friend_trial_package.bat",
    ],
)
def test_obsolete_batch_entrypoints_reject(entrypoint: str) -> None:
    completed = _run(["cmd.exe", "/d", "/c", str(ROOT / entrypoint)])

    assert completed.returncode == 2
    assert "Obsolete workflow blocked" in completed.stderr
    assert PRODUCT_REPOSITORY in completed.stderr


@pytest.mark.skipif(sys.platform != "win32", reason="Windows command entrypoints")
@pytest.mark.parametrize(
    "entrypoint",
    [
        "tools/prepare_windows_yime_lexicon.ps1",
        "tools/export_and_deploy_weasel_yime.ps1",
    ],
)
def test_obsolete_powershell_entrypoints_reject(entrypoint: str) -> None:
    completed = _run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            entrypoint,
        ]
    )
    normalized_stderr = " ".join(completed.stderr.split())

    assert completed.returncode == 2
    assert "Obsolete workflow blocked" in normalized_stderr
    assert PRODUCT_REPOSITORY in normalized_stderr


def test_direct_pyinstaller_spec_is_blocked_without_pyinstaller() -> None:
    completed = _run([sys.executable, "yime_portable.spec"])

    assert completed.returncode != 0
    assert "Obsolete workflow blocked" in completed.stderr
    assert PRODUCT_REPOSITORY in completed.stderr


def test_declarative_release_entrypoints_are_blocked() -> None:
    setup_spec = (ROOT / "yime_setup.iss").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/release.yml").read_text(
        encoding="utf-8"
    )

    assert '#error "Obsolete workflow blocked' in setup_spec
    assert "release:" not in workflow
    assert "exit 2" in workflow
    assert PRODUCT_REPOSITORY in workflow
