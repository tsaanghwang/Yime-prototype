import hashlib
import json
from pathlib import Path

from tools.verify_default_runtime_handoff import verify_handoff


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_verify_handoff_accepts_matching_three_mode_runtime(tmp_path: Path) -> None:
    prototype = tmp_path / "prototype"
    windows = tmp_path / "windows"
    data = windows / "go-backend" / "input_methods" / "yime" / "data"
    generated = prototype / ".generated"
    dictionaries = [
        "yime_full.dict.yaml",
        "yime_variable.dict.yaml",
        "yime_shorthand.dict.yaml",
    ]
    sidecars = [
        "yime_pinyin_codes.tsv",
        "yime_syllable_decomposition.tsv",
        "pinyin_normalized.json",
        "yime_pua_pinyin.json",
    ]
    output_hashes = {}
    for name in dictionaries:
        path = data / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(name.encode())
        output_hashes[name] = _sha256(path)
    for name in sidecars:
        prototype_path = generated / "windows_yime_import" / name
        windows_path = data / name
        prototype_path.parent.mkdir(parents=True, exist_ok=True)
        prototype_path.write_bytes(name.encode())
        windows_path.write_bytes(name.encode())

    source_sha = hashlib.sha256(b"source").hexdigest()
    ranking = {
        "direct_bcc": 3,
        "provisional_rime_lmdg": 4,
        "provisional_structural_floor": 1,
    }
    _write_json(
        prototype / "internal_data" / "runtime_lexicon_filter_policy.json",
        {
            "policy_id": "test",
            "runtime_handoff": {
                "default_schema": "yime_variable",
                "runtime_schemas": ["yime_variable", "yime_full", "yime_shorthand"],
                "windows_dictionaries": dictionaries,
                "sidecar_files": sidecars,
                "legacy_large_lexicons_packaged": False,
            },
        },
    )
    _write_json(
        prototype / "internal_data" / "manual_key_layout.json",
        {
            "layers": [
                {"yinyuan_id": "N01", "display_label": "b"},
                {"yinyuan_id": "N12", "display_label": "'"},
            ],
            "shared_yinyuan_key_groups": [
                {
                    "owner_yinyuan_id": "N12",
                    "member_yinyuan_ids": ["N12", "N26"],
                }
            ],
        },
    )
    _write_json(
        generated / "two_level_runtime_trial" / "dictionary.manifest.json",
        {
            "output_sha256": source_sha,
            "total_reading_entries": 8,
            "total_distinct_texts": 7,
            "ranking_evidence": {"distinct_texts_by_source": ranking},
        },
    )
    _write_json(
        data / "yime_runtime_profile.json",
        {
            "default_schema": "yime_variable",
            "runtime_schemas": ["yime_variable", "yime_full", "yime_shorthand"],
            "runtime_manifest": "yime_lexicon_manifest.json",
            "source_evidence_manifest": "yime_core_source_manifest.json",
            "prototype_policy": "internal_data/runtime_lexicon_filter_policy.json",
            "entry_count_per_mode": 8,
            "distinct_core_texts": 7,
            "ranking_evidence": ranking,
        },
    )
    _write_json(
        data / "yime_lexicon_manifest.json",
        {"source_sha256": source_sha, "entry_count": 8, "output_sha256": output_hashes},
    )
    _write_json(
        data / "yime_core_source_manifest.json",
        {
            "source_dictionary_sha256": source_sha,
            "entry_count": 8,
            "distinct_texts": 7,
            "ranking_evidence": ranking,
        },
    )
    _write_json(
        data / "yime_yinyuan_layout.json",
        {"yinyuan_id_to_key": {"N01": "b", "N12": "'", "N26": "'"}},
    )

    result = verify_handoff(prototype, windows)

    assert result["status"] == "passed"
    assert result["entry_count"] == 8
    assert result["runtime_schemas"] == ["yime_variable", "yime_full", "yime_shorthand"]
