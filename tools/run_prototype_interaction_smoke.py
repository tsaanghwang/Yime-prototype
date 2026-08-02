#!/usr/bin/env python3
"""Run the repository's headless prototype interaction smoke scenarios."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "internal_data" / "prototype_smoke_scenarios.json"
DEFAULT_OUTPUT = ROOT / ".generated" / "prototype_interaction_smoke" / "report.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--scenario", action="append", default=[])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    constraints = manifest.get("constraints", {})
    required = {
        "gui_automation": False,
        "restart_allowed": False,
        "windows_yime_export_allowed": False,
        "real_user_directory_allowed": False,
    }
    if constraints != required:
        raise ValueError(f"unsafe or incomplete smoke constraints: {constraints!r}")
    selected = set(args.scenario)
    scenarios = [
        scenario
        for scenario in manifest["scenarios"]
        if not selected or scenario["id"] in selected
    ]
    unknown = selected - {scenario["id"] for scenario in scenarios}
    if unknown:
        raise ValueError(f"unknown smoke scenarios: {sorted(unknown)}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    results = []
    overall_passed = True
    for scenario in scenarios:
        cache_dir = args.output.parent / "pytest-cache" / scenario["id"]
        command = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-o",
            f"cache_dir={cache_dir}",
            *scenario["tests"],
        ]
        started = time.monotonic()
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        duration = round(time.monotonic() - started, 3)
        passed = completed.returncode == 0
        overall_passed = overall_passed and passed
        results.append(
            {
                "id": scenario["id"],
                "coverage": scenario["coverage"],
                "tests": scenario["tests"],
                "passed": passed,
                "returncode": completed.returncode,
                "duration_seconds": duration,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            }
        )
        print(f"{scenario['id']}: {'PASS' if passed else 'FAIL'} ({duration:.3f}s)")

    report = {
        "schema_version": 1,
        "policy_id": manifest["policy_id"],
        "manifest": str(args.manifest.resolve()),
        "constraints": constraints,
        "scenario_count": len(results),
        "passed_count": sum(result["passed"] for result in results),
        "decision": "complete" if overall_passed else "failed",
        "scenarios": results,
    }
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"report: {args.output.resolve()}")
    return 0 if overall_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())