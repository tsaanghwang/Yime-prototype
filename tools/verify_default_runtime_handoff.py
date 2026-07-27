#!/usr/bin/env python3
"""Verify the compact runtime handoff from the prototype to Yime for Windows."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_handoff(prototype_root: Path, windows_repo: Path) -> dict[str, Any]:
    policy = _read_json(
        prototype_root / "internal_data" / "runtime_lexicon_filter_policy.json"
    )
    data_dir = windows_repo / "go-backend" / "input_methods" / "yime" / "data"
    profile = _read_json(data_dir / "yime_runtime_profile.json")
    handoff = policy["runtime_handoff"]
    if profile["default_schema"] != handoff["default_schema"]:
        raise ValueError("prototype policy and Windows default schema disagree")
    if profile["prototype_policy"] != "internal_data/runtime_lexicon_filter_policy.json":
        raise ValueError("Windows runtime profile does not identify the prototype policy")
    if handoff["legacy_large_lexicons_packaged"]:
        raise ValueError("legacy large lexicons must not be marked for packaging")

    dictionary_path = data_dir / profile["runtime_dictionary"]
    manifest = _read_json(data_dir / profile["runtime_manifest"])
    expected_hash = manifest["output_sha256"][dictionary_path.name]
    actual_hash = _sha256(dictionary_path)
    if actual_hash != expected_hash:
        raise ValueError(
            f"runtime dictionary hash mismatch: expected {expected_hash}, got {actual_hash}"
        )

    target = float(profile["acceptance"]["target_dynamic_sentence_rate"])
    lower_bound = float(policy["evaluation"]["wilson_95_lower_bound"])
    if lower_bound < target:
        raise ValueError(
            f"replay lower confidence bound {lower_bound:.6f} is below target {target:.6f}"
        )

    declared_offline = set(profile["offline_only_files"])
    required_offline = {
        "yime_full.dict.yaml",
        "yime_variable.dict.yaml",
        "yime_shorthand.dict.yaml",
    }
    missing = sorted(required_offline - declared_offline)
    if missing:
        raise ValueError(f"legacy dictionaries not declared offline-only: {missing}")

    return {
        "status": "passed",
        "policy_id": policy["policy_id"],
        "default_schema": profile["default_schema"],
        "entry_count": int(manifest["entry_count"]),
        "dictionary_sha256": actual_hash,
        "target_dynamic_sentence_rate": target,
        "replay_wilson_95_lower_bound": lower_bound,
        "offline_only_files": sorted(declared_offline),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--windows-repo",
        type=Path,
        default=Path(r"C:\dev\Yime"),
        help="Yime for Windows repository root",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = verify_handoff(ROOT, args.windows_repo.resolve())
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
