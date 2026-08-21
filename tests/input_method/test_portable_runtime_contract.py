from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_portable_build_requires_windows_parity_runtime() -> None:
    build_script = (ROOT / "scripts/build_portable_release.bat").read_text(
        encoding="utf-8"
    )
    spec = (ROOT / "yime_portable.spec").read_text(encoding="utf-8")

    assert "tools\\prepare_prototype_windows_parity.py" in build_script
    assert "prototype_runtime_manifest.json" in spec
    assert 'Path(item[0]).name.startswith("pinyin_hanzi.db")' in spec
    assert 'datas.append((str(parity_database), "yime"))' in spec


def test_default_profile_is_windows_variable_parity() -> None:
    payload = json.loads(
        (ROOT / "internal_data/prototype_runtime_profile.json").read_text(
            encoding="utf-8"
        )
    )

    assert payload["default_profile"] == "windows_parity"
    parity = payload["profiles"]["windows_parity"]
    assert parity["windows_schema"] == "yime_variable"
    assert parity["default_code_mode"] == "variable"
    assert payload["profiles"]["research_full"]["packaged"] is False
