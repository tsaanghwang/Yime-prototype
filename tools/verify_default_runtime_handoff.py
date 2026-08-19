#!/usr/bin/env python3
"""Verify the current three-mode runtime handoff to Yime for Windows."""

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


def _layout_digest(mapping: dict[str, str]) -> str:
    payload = json.dumps(
        sorted(mapping.items()),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _prototype_layout_mapping(path: Path) -> dict[str, str]:
    layout = _read_json(path)
    mapping = {
        str(layer["yinyuan_id"]): str(layer["display_label"])
        for layer in layout["layers"]
        if layer.get("yinyuan_id")
    }
    for group in layout.get("shared_yinyuan_key_groups", []):
        owner = str(group["owner_yinyuan_id"])
        owner_key = mapping[owner]
        for member in group["member_yinyuan_ids"]:
            mapping[str(member)] = owner_key
    return mapping


def _require_equal(label: str, left: Any, right: Any) -> None:
    if left != right:
        raise ValueError(f"{label} mismatch: prototype={left!r}, Windows={right!r}")


def verify_handoff(prototype_root: Path, windows_repo: Path) -> dict[str, Any]:
    policy = _read_json(
        prototype_root / "internal_data" / "runtime_lexicon_filter_policy.json"
    )
    prototype_manifest = _read_json(
        prototype_root
        / ".generated"
        / "two_level_runtime_trial"
        / "dictionary.manifest.json"
    )
    data_dir = windows_repo / "go-backend" / "input_methods" / "yime" / "data"
    profile = _read_json(data_dir / "yime_runtime_profile.json")
    runtime_manifest = _read_json(data_dir / profile["runtime_manifest"])
    source_manifest = _read_json(data_dir / profile["source_evidence_manifest"])
    handoff = policy["runtime_handoff"]

    _require_equal(
        "default schema", handoff["default_schema"], profile["default_schema"]
    )
    _require_equal(
        "runtime schemas", handoff["runtime_schemas"], profile["runtime_schemas"]
    )
    if profile["prototype_policy"] != "internal_data/runtime_lexicon_filter_policy.json":
        raise ValueError("Windows runtime profile does not identify the prototype policy")
    if handoff["legacy_large_lexicons_packaged"]:
        raise ValueError("legacy source lexicons must not be marked for packaging")

    source_sha = str(prototype_manifest["output_sha256"])
    _require_equal("core source SHA", source_sha, runtime_manifest["source_sha256"])
    _require_equal(
        "core source manifest SHA",
        source_sha,
        source_manifest["source_dictionary_sha256"],
    )
    _require_equal(
        "core entry count",
        int(prototype_manifest["total_reading_entries"]),
        int(runtime_manifest["entry_count"]),
    )
    _require_equal(
        "source entry count",
        int(prototype_manifest["total_reading_entries"]),
        int(source_manifest["entry_count"]),
    )
    _require_equal(
        "profile entry count",
        int(prototype_manifest["total_reading_entries"]),
        int(profile["entry_count_per_mode"]),
    )
    _require_equal(
        "distinct text count",
        int(prototype_manifest["total_distinct_texts"]),
        int(source_manifest["distinct_texts"]),
    )
    _require_equal(
        "profile distinct text count",
        int(prototype_manifest["total_distinct_texts"]),
        int(profile["distinct_core_texts"]),
    )

    expected_ranking = prototype_manifest["ranking_evidence"][
        "distinct_texts_by_source"
    ]
    for key in (
        "direct_bcc",
        "provisional_rime_lmdg",
        "provisional_structural_floor",
    ):
        _require_equal(
            f"ranking count {key}",
            int(expected_ranking[key]),
            int(source_manifest["ranking_evidence"][key]),
        )
        _require_equal(
            f"profile ranking count {key}",
            int(expected_ranking[key]),
            int(profile["ranking_evidence"][key]),
        )

    output_hashes: dict[str, str] = {}
    for name in handoff["windows_dictionaries"]:
        expected_hash = runtime_manifest["output_sha256"][name]
        actual_hash = _sha256(data_dir / name)
        if actual_hash != expected_hash:
            raise ValueError(
                f"runtime dictionary hash mismatch for {name}: "
                f"expected {expected_hash}, got {actual_hash}"
            )
        output_hashes[name] = actual_hash

    prototype_layout = _prototype_layout_mapping(
        prototype_root / "internal_data" / "manual_key_layout.json"
    )
    windows_layout = _read_json(data_dir / "yime_yinyuan_layout.json")[
        "yinyuan_id_to_key"
    ]
    _require_equal("Yinyuan layout mapping", prototype_layout, windows_layout)
    layout_digest = _layout_digest(prototype_layout)

    sidecar_hashes: dict[str, str] = {}
    prototype_sidecars = prototype_root / ".generated" / "windows_yime_import"
    for name in handoff["sidecar_files"]:
        prototype_hash = _sha256(prototype_sidecars / name)
        windows_hash = _sha256(data_dir / name)
        _require_equal(f"sidecar SHA {name}", prototype_hash, windows_hash)
        sidecar_hashes[name] = windows_hash

    return {
        "status": "passed",
        "policy_id": policy["policy_id"],
        "default_schema": profile["default_schema"],
        "runtime_schemas": profile["runtime_schemas"],
        "entry_count": int(runtime_manifest["entry_count"]),
        "distinct_texts": int(source_manifest["distinct_texts"]),
        "source_dictionary_sha256": source_sha,
        "layout_digest": layout_digest,
        "output_sha256": output_hashes,
        "sidecar_sha256": sidecar_hashes,
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
