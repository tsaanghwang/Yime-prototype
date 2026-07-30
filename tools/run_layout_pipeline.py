"""Compatibility entrypoint for the locked keyboard-layout pipeline."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
LOCKED_PIPELINE = ROOT / "tools" / "run_locked_layout_pipeline.py"


def main() -> int:
    if len(sys.argv) > 1:
        print(
            "Direct/custom layout-pipeline arguments are locked. "
            "Edit internal_data/manual_key_layout.json and run "
            "python tools/run_locked_layout_pipeline.py."
        )
        return 2
    return subprocess.run(
        [sys.executable, str(LOCKED_PIPELINE)],
        cwd=ROOT,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
