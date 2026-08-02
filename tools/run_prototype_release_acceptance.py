#!/usr/bin/env python3
"""Run an isolated, non-Windows-handoff prototype rebuild and acceptance gate."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "internal_data" / "prototype_release_acceptance_policy.json"
DEFAULT_OUTPUT_ROOT = ROOT / ".generated" / "prototype_release_acceptance"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--skip-full-data", action="store_true")
    parser.add_argument(
        "--reuse-rebuild-from",
        type=Path,
        help="Reuse source/input/recursive/capacity outputs from an interrupted full run.",
    )
    parser.add_argument("--require-clean", action="store_true")
    return parser.parse_args()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _nested(payload: dict[str, Any], path: str) -> Any:
    value: Any = payload
    for part in path.split("."):
        value = value[part]
    return value


def _assert_safe_command(command: list[str], forbidden: set[str]) -> None:
    basenames = {Path(argument).name.lower() for argument in command}
    blocked = sorted(basenames & forbidden)
    if blocked:
        raise ValueError(f"forbidden external handoff command: {blocked}")
    lowered = " ".join(command).lower()
    for token in ("shutdown.exe", "restart-computer", "restart-service"):
        if token in lowered:
            raise ValueError(f"restart-capable command is forbidden: {token}")


def _compare_json_to_baseline(
    actual_path: Path,
    expected: dict[str, Any],
    fields: list[str],
) -> dict[str, Any]:
    actual = _load_json(actual_path)
    mismatches = []
    for field in fields:
        if _nested(actual, field) != _nested(expected, field):
            mismatches.append(field)
    if mismatches:
        raise AssertionError(f"generated artifact drift from tracked baseline: {actual_path}: {mismatches}")
    return {"actual": str(actual_path), "baseline_fields": fields}


def _input_model_counts(path: Path) -> dict[str, Any]:
    uri = path.resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        return {
            "candidate_universe": connection.execute(
                "SELECT COUNT(*) FROM candidate_universe"
            ).fetchone()[0],
            "assessments": connection.execute(
                "SELECT COUNT(*) FROM assessments"
            ).fetchone()[0],

            "dynamic_reachable": [
                list(row)
                for row in connection.execute(
                    "SELECT dynamic_reachable, COUNT(*) FROM candidate_universe GROUP BY 1 ORDER BY 1"
                ).fetchall()
            ],
        }


def _make_run_directory(output_root: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    candidate = output_root / stamp
    suffix = 1
    while candidate.exists():
        candidate = output_root / f"{stamp}-{suffix}"
        suffix += 1
    candidate.mkdir(parents=True)
    return candidate


def main() -> int:
    args = parse_args()
    policy = _load_json(POLICY_PATH)
    baseline = _load_json(ROOT / policy["baseline"])
    if args.skip_full_data and args.reuse_rebuild_from:
        raise ValueError("--skip-full-data and --reuse-rebuild-from are mutually exclusive")
    expected_safeguards = {
        "restart_allowed": False,
        "windows_yime_export_allowed": False,
        "canonical_generated_files_mutated": False,
        "existing_gates_removed": False,
    }
    if policy["safeguards"] != expected_safeguards:
        raise ValueError("acceptance safeguards are incomplete")
    forbidden = {name.lower() for name in policy["forbidden_entrypoints"]}
    run_directory = _make_run_directory(args.output_root.resolve())
    manifest_path = run_directory / "acceptance_manifest.json"
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    steps: list[dict[str, Any]] = []
    comparisons: list[dict[str, Any]] = []
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "policy_id": policy["policy_id"],
        "mode": (
            "existing_artifacts"
            if args.skip_full_data
            else "reused_rebuild"
            if args.reuse_rebuild_from
            else "full_rebuild"
        ),
        "run_directory": str(run_directory),
        "safeguards": expected_safeguards,
        "steps": steps,
        "comparisons": comparisons,
        "decision": "running",
    }

    def write_manifest() -> None:
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def run_step(name: str, command: list[str]) -> None:
        _assert_safe_command(command, forbidden)
        print(f"START {name}", flush=True)
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
        stdout_path = run_directory / f"{name}.stdout.log"
        stderr_path = run_directory / f"{name}.stderr.log"
        stdout_path.write_text(completed.stdout, encoding="utf-8")
        stderr_path.write_text(completed.stderr, encoding="utf-8")
        step = {
            "name": name,
            "command": command,
            "returncode": completed.returncode,
            "duration_seconds": duration,
            "stdout": str(stdout_path),
            "stderr": str(stderr_path),
            "passed": completed.returncode == 0,
        }
        steps.append(step)
        write_manifest()
        print(f"{'PASS' if step['passed'] else 'FAIL'} {name} ({duration:.3f}s)", flush=True)
        if not step["passed"]:
            raise RuntimeError(f"step failed: {name}; see {stderr_path}")

    try:
        if args.require_clean:
            completed = subprocess.run(
                ["git", "status", "--porcelain", "--untracked-files=all"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if completed.returncode != 0 or completed.stdout.strip():
                raise RuntimeError("--require-clean failed: worktree is not clean")

        run_step("git_diff_check", ["git", "diff", "--check"])

        audit_dir = run_directory / "syllable_audit"
        run_step(
            "syllable_audit_export",
            [
                sys.executable,
                "tools/export_syllable_decomposition.py",
                "--output",
                str(audit_dir / "yime_syllable_decomposition.tsv"),
                "--omissions-output",
                str(audit_dir / "yime_syllable_omissions.tsv"),
                "--provenance-output",
                str(audit_dir / "yime_syllable_encoding_provenance.tsv"),
            ],
        )
        for filename in (
            "yime_syllable_decomposition.tsv",
            "yime_syllable_omissions.tsv",
            "yime_syllable_encoding_provenance.tsv",
        ):
            actual = audit_dir / filename
            canonical = ROOT / "internal_data" / filename
            if actual.read_bytes() != canonical.read_bytes():
                raise AssertionError(f"syllable audit drift: {filename}")
            comparisons.append(
                {"actual": str(actual), "canonical": str(canonical), "comparison": "bytes"}
            )
        run_step("layout_change_lock", [sys.executable, "tools/check_layout_change_lock.py"])

        for document, anchors in policy["documentation_anchors"].items():
            text = (ROOT / document).read_text(encoding="utf-8")
            missing = [anchor for anchor in anchors if anchor not in text]
            if missing:
                raise AssertionError(f"documentation drift in {document}: {missing}")
        steps.append({"name": "documentation_anchors", "passed": True})

        canonical = {
            key: ROOT / value for key, value in policy["canonical_artifacts"].items()
        }
        if args.skip_full_data:
            missing = [str(path) for path in canonical.values() if not path.is_file()]
            if missing:
                raise FileNotFoundError(f"missing canonical artifacts: {missing}")
            source_database = ROOT / ".generated/lexicon_source_bundle/source_lexicon.sqlite3"
            input_database = ROOT / ".generated/input_candidate_model/input_model.sqlite3"
            capacity_database = ROOT / ".generated/static_lexicon_capacity/static_capacity.sqlite3"
            selection = ROOT / ".generated/two_level_runtime_trial/selection.tsv"
            source_manifest = canonical["source_manifest"]
            recursive_manifest = canonical["recursive_manifest"]
            capacity_manifest = canonical["capacity_manifest"]
            runtime_manifest = canonical["runtime_manifest"]
        elif args.reuse_rebuild_from:
            reuse = args.reuse_rebuild_from.resolve()
            source_database = reuse / "source_bundle" / "source_lexicon.sqlite3"
            source_manifest = reuse / "source_bundle" / "manifest.json"
            input_database = reuse / "input_model.sqlite3"
            recursive_manifest = reuse / "recursive_composition" / "manifest.json"
            capacity_database = reuse / "static_capacity" / "static_capacity.sqlite3"
            capacity_manifest = reuse / "static_capacity" / "manifest.json"
            required = (
                source_database,
                source_manifest,
                input_database,
                recursive_manifest,
                capacity_database,
                capacity_manifest,
            )
            missing = [str(path) for path in required if not path.is_file()]
            if missing:
                raise FileNotFoundError(f"incomplete reusable rebuild: {missing}")
            run_step(
                "refresh_syllable_inventory",
                [
                    sys.executable,
                    "tools/refresh_materialized_syllable_inventory.py",
                    "--db-path",
                    str(source_database),
                ],
            )
            runtime_dir = run_directory / "trial"
            run_step(
                "build_two_level_trial",
                [
                    sys.executable,
                    "tools/build_two_level_runtime_trial.py",
                    "--source-database",
                    str(source_database),
                    "--capacity-database",
                    str(capacity_database),
                    "--input-model-database",
                    str(input_database),
                    "--output-dir",
                    str(runtime_dir),
                    "--skip-runtime-database",
                ],
            )
            selection = runtime_dir / "selection.tsv"
            runtime_manifest = runtime_dir / "manifest.json"
        else:
            source_dir = run_directory / "source_bundle"
            input_database = run_directory / "input_model.sqlite3"
            recursive_dir = run_directory / "recursive_composition"
            capacity_dir = run_directory / "static_capacity"
            runtime_dir = run_directory / "trial"
            run_step(
                "build_source_bundle",
                [sys.executable, "tools/build_lexicon_source_bundle.py", "--output-dir", str(source_dir)],
            )
            source_database = source_dir / "source_lexicon.sqlite3"
            source_manifest = source_dir / "manifest.json"
            run_step(
                "refresh_syllable_inventory",
                [
                    sys.executable,
                    "tools/refresh_materialized_syllable_inventory.py",
                    "--db-path",
                    str(source_database),
                ],
            )
            run_step(
                "build_input_model",
                [
                    sys.executable,
                    "tools/build_input_candidate_model.py",
                    "--source-database",
                    str(source_database),
                    "--output-database",
                    str(input_database),
                ],
            )
            run_step(
                "build_recursive_composition",
                [
                    sys.executable,
                    "tools/build_recursive_composition_model.py",
                    "--source-database",
                    str(source_database),
                    "--input-model-database",
                    str(input_database),
                    "--output-dir",
                    str(recursive_dir),
                ],
            )
            recursive_manifest = recursive_dir / "manifest.json"
            run_step(
                "build_static_capacity",
                [
                    sys.executable,
                    "tools/plan_static_lexicon_capacity.py",
                    "--source-database",
                    str(source_database),
                    "--output-dir",
                    str(capacity_dir),
                ],
            )
            capacity_database = capacity_dir / "static_capacity.sqlite3"
            capacity_manifest = capacity_dir / "manifest.json"
            run_step(
                "build_two_level_trial",
                [
                    sys.executable,
                    "tools/build_two_level_runtime_trial.py",
                    "--source-database",
                    str(source_database),
                    "--capacity-database",
                    str(capacity_database),
                    "--input-model-database",
                    str(input_database),
                    "--output-dir",
                    str(runtime_dir),
                    "--skip-runtime-database",
                ],
            )
            selection = runtime_dir / "selection.tsv"
            runtime_manifest = runtime_dir / "manifest.json"

        source_uri = source_database.resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(source_uri, uri=True) as connection:
            inventory_count = connection.execute(
                "SELECT COUNT(*) FROM m_distinct_syllable_inventory"
            ).fetchone()[0]
        if inventory_count < 1:
            raise AssertionError("materialized syllable inventory is empty")
        steps.append(
            {"name": "materialized_syllable_inventory", "passed": True, "rows": inventory_count}
        )

        report_dir = run_directory / "reports"
        second_dir = report_dir / "second_batch"
        ranking_report = report_dir / "ranking.json"
        dynamic_report = report_dir / "dynamic.json"
        run_step(
            "export_second_batch",
            [
                sys.executable,
                "tools/export_second_batch_bcc_review.py",
                "--source-database",
                str(source_database),
                "--input-model-database",
                str(input_database),
                "--output-directory",
                str(second_dir),
            ],
        )
        run_step(
            "evaluate_ranking",
            [
                sys.executable,
                "tools/evaluate_candidate_ranking_evidence.py",
                "--source-database",
                str(source_database),
                "--capacity-database",
                str(capacity_database),
                "--selection",
                str(selection),
                "--output",
                str(ranking_report),
            ],
        )
        run_step(
            "evaluate_dynamic_coverage",
            [
                sys.executable,
                "tools/evaluate_dynamic_candidate_coverage.py",
                "--capacity-database",
                str(capacity_database),
                "--input-model-database",
                str(input_database),
                "--selection",
                str(selection),
                "--output",
                str(dynamic_report),
            ],
        )

        comparison_specs = [
            (source_manifest, baseline["source"], ["counts", "source_gate_counts"]),
            (recursive_manifest, baseline["recursive"], ["configuration", "counts"]),
            (capacity_manifest, baseline["capacity"], ["configuration", "counts", "recommendation"]),
            (
                runtime_manifest,
                baseline["trial"],
                [
                    "candidate_ranking_evidence.decision",
                    "candidate_ranking_evidence.selected_counts",
                    "dynamic_candidate_coverage.decision",
                    "dynamic_candidate_coverage.level_counts",
                    "first_level.distinct_texts_by_length",
                    "first_level.total_distinct_texts",
                    "first_level.total_reading_entries",
                    "dictionary.distinct_texts_by_length",
                    "dictionary.total_distinct_texts",
                    "dictionary.total_reading_entries",
                ],
            ),
            (
                ranking_report,
                baseline["ranking"],
                [
                    "decision",
                    "result.classified_selected_texts",
                    "result.completion_passed",
                    "result.full_inventory_counts",
                    "result.maximum_provisional_lmdg_effective_weight",
                    "result.maximum_provisional_structural_effective_weight",
                    "result.minimum_direct_bcc_effective_weight",
                    "result.missing_selected_source_texts",
                    "result.raw_bcc_and_lmdg_values_added",
                    "result.selected_counts",
                    "result.selected_texts",
                    "result.selection_evidence_columns_present",
                    "result.source_priority_separation_passed",
                ],
            ),
            (
                dynamic_report,
                baseline["dynamic"],
                [
                    "decision",
                    "result.classified_selected_texts",
                    "result.classified_texts",
                    "result.completion_passed",
                    "result.encoded_texts",
                    "result.level_counts",
                    "result.level_frequency",
                    "result.outside_encoded_capacity_texts",
                    "result.selected_counts",
                    "result.selected_texts",
                ],
            ),
            (
                second_dir / "manifest.json",
                baseline["second_batch"],
                ["frequency_range", "counts", "safeguards", "decision"],
            ),
        ]
        for actual, expected, fields in comparison_specs:
            comparisons.append(_compare_json_to_baseline(actual, expected, fields))
        actual_input_counts = _input_model_counts(input_database)
        if actual_input_counts != baseline["input_model"]:
            raise AssertionError(
                f"input model drift from tracked baseline: {actual_input_counts} != {baseline['input_model']}"
            )
        comparisons.append(
            {"actual": str(input_database), "baseline": "input_model", "counts": actual_input_counts}
        )
        steps.append({"name": "generated_artifact_drift", "passed": True})
        write_manifest()

        run_step(
            "interaction_smoke",
            [
                sys.executable,
                "tools/run_prototype_interaction_smoke.py",
                "--output",
                str(run_directory / "interaction_smoke.json"),
            ],
        )
        run_step(
            "pytest",
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "-o",
                f"cache_dir={run_directory / 'pytest-cache'}",
            ],
        )
        manifest["decision"] = "complete"
        manifest["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
        write_manifest()
        print(f"PASS prototype release acceptance: {manifest_path}", flush=True)
        return 0
    except Exception as exc:
        manifest["decision"] = "failed"
        manifest["error"] = f"{type(exc).__name__}: {exc}"
        manifest["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
        write_manifest()
        print(f"FAIL prototype release acceptance: {exc}", file=sys.stderr, flush=True)
        print(f"manifest: {manifest_path}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())