"""The only supported entrypoint for changing the Yinyuan keyboard layout."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"


def run_step(name: str, *arguments: str) -> None:
    command = [sys.executable, *arguments]
    print(f"[{name}] {' '.join(command)}")
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> int:
    run_step(
        "1/8 semantic and source lock",
        str(TOOLS / "check_layout_change_lock.py"),
        "--preflight",
    )
    run_step(
        "2/8 resolve canonical layout",
        str(TOOLS / "resolve_manual_key_layout.py"),
    )
    run_step(
        "3/8 runtime consistency",
        str(TOOLS / "check_layout_runtime_consistency.py"),
        "--json-output",
        str(ROOT / "internal_data" / "layout_runtime_consistency_report.json"),
    )
    run_step(
        "4/8 generate KLC",
        str(TOOLS / "generate_klc_from_manual_layout.py"),
        "--symbol-mode",
        "bmp-trial",
        "--ligature-mode",
        "clean",
    )
    run_step(
        "5/8 export visual table",
        str(TOOLS / "export_klc_visual_table.py"),
    )
    run_step(
        "6/8 regenerate crosswalk",
        str(TOOLS / "generate_yinyuan_id_crosswalk_report.py"),
    )
    run_step(
        "7/8 validate Yinyuan sources",
        str(TOOLS / "validate_yinyuan_source_consistency.py"),
    )
    run_step(
        "8/8 close layout change lock",
        str(TOOLS / "check_layout_change_lock.py"),
    )
    print("Locked layout pipeline completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

