import hashlib
import json
from pathlib import Path

from tools.verify_default_runtime_handoff import verify_handoff


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_verify_handoff_accepts_matching_compact_runtime(tmp_path: Path) -> None:
    prototype = tmp_path / "prototype"
    windows = tmp_path / "windows"
    data = windows / "go-backend" / "input_methods" / "yime" / "data"
    dictionary = data / "yime_core_trial.dict.yaml"
    dictionary.parent.mkdir(parents=True)
    dictionary.write_bytes(b"compact-runtime")
    digest = hashlib.sha256(dictionary.read_bytes()).hexdigest()

    _write_json(
        prototype / "internal_data" / "runtime_lexicon_filter_policy.json",
        {
            "policy_id": "test",
            "evaluation": {"wilson_95_lower_bound": 0.993},
            "runtime_handoff": {
                "default_schema": "yime_core_trial",
                "legacy_large_lexicons_packaged": False,
            },
        },
    )
    _write_json(
        data / "yime_runtime_profile.json",
        {
            "default_schema": "yime_core_trial",
            "runtime_dictionary": dictionary.name,
            "runtime_manifest": "yime_core_trial_manifest.json",
            "prototype_policy": "internal_data/runtime_lexicon_filter_policy.json",
            "offline_only_files": [
                "yime_full.dict.yaml",
                "yime_variable.dict.yaml",
                "yime_shorthand.dict.yaml",
            ],
            "acceptance": {"target_dynamic_sentence_rate": 0.99},
        },
    )
    _write_json(
        data / "yime_core_trial_manifest.json",
        {
            "entry_count": 1124631,
            "output_sha256": {dictionary.name: digest},
        },
    )

    result = verify_handoff(prototype, windows)

    assert result["status"] == "passed"
    assert result["entry_count"] == 1124631
