from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.prepare_windows_yime_auxiliary_assets import prepare_assets


def _write_fixture_assets(repo_root: Path, *, normalized: dict[str, str]) -> None:
    internal_data = repo_root / "internal_data"
    yime_dir = repo_root / "yime"
    internal_data.mkdir(parents=True)
    yime_dir.mkdir(parents=True)
    (internal_data / "yime_syllable_decomposition.tsv").write_text(
        "pinyin_tone\tmarked_pinyin\n"
        "a1\tā\n"
        "a2\tá\n",
        encoding="utf-8",
    )
    (yime_dir / "pinyin_normalized.json").write_text(
        json.dumps(normalized, ensure_ascii=False),
        encoding="utf-8",
    )
    (yime_dir / "code_pinyin.json").write_text(
        json.dumps({"PUA-A": ["a1"], "PUA-B": ["a2"]}),
        encoding="utf-8",
    )


def test_prepare_assets_copies_complete_audited_set(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    output_dir = tmp_path / "handoff"
    _write_fixture_assets(repo_root, normalized={"a1": "ā", "a2": "á"})
    output_dir.mkdir()
    (output_dir / "yime_pinyin_codes.tsv").write_text(
        "pinyin_tone\tfull\na1\t'fff\n",
        encoding="utf-8",
    )

    manifest = prepare_assets(output_dir, repo_root=repo_root)

    assert manifest["audited_pinyin_inventory_count"] == 2
    assert manifest["layout_code_inventory_count"] == 1
    assert manifest["audited_pinyin_without_layout_code"] == ["a2"]
    assert (output_dir / "yime_syllable_decomposition.tsv").is_file()
    assert (output_dir / "pinyin_normalized.json").is_file()
    assert (output_dir / "yime_pua_pinyin.json").is_file()
    assert (output_dir / "yime_handoff_manifest.json").is_file()
    assert {asset["name"] for asset in manifest["assets"]} == {
        "yime_syllable_decomposition.tsv",
        "pinyin_normalized.json",
        "yime_pua_pinyin.json",
        "yime_pinyin_codes.tsv",
    }


def test_prepare_assets_rejects_disagreeing_audited_inventories(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    output_dir = tmp_path / "handoff"
    _write_fixture_assets(repo_root, normalized={"a1": "ā"})
    output_dir.mkdir()
    (output_dir / "yime_pinyin_codes.tsv").write_text(
        "pinyin_tone\tfull\na1\t'fff\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="auxiliary pinyin inventories disagree"):
        prepare_assets(output_dir, repo_root=repo_root)
