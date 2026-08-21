from __future__ import annotations

import json
from pathlib import Path

import pytest

from yime.input_method.core.decoders import CompositeCandidateDecoder
from yime.input_method.runtime_profile import resolve_runtime_profile


def _write_profile(repo_root: Path) -> None:
    path = repo_root / "internal_data" / "prototype_runtime_profile.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "default_profile": "windows_parity",
                "profiles": {
                    "windows_parity": {
                        "source_database": ".generated/parity/runtime.db",
                        "packaged_database": "yime/pinyin_hanzi.db",
                        "manifest": ".generated/parity/manifest.json",
                        "windows_schema": "yime_variable",
                    },
                    "research_full": {
                        "source_database": "yime/pinyin_hanzi.db",
                        "packaged": False,
                    },
                },
            }
        ),
        encoding="utf-8",
    )


def test_source_runtime_defaults_to_windows_parity(tmp_path: Path) -> None:
    app_dir = tmp_path / "yime"
    app_dir.mkdir()
    _write_profile(tmp_path)

    result = resolve_runtime_profile(
        app_dir,
        repo_root=tmp_path,
        env={},
        is_frozen=False,
    )

    assert result.profile_id == "windows_parity"
    assert result.database_path == tmp_path / ".generated/parity/runtime.db"
    assert result.manifest_path == tmp_path / ".generated/parity/manifest.json"
    assert result.windows_schema == "yime_variable"


def test_research_full_profile_is_explicit_source_only(tmp_path: Path) -> None:
    app_dir = tmp_path / "yime"
    app_dir.mkdir()
    _write_profile(tmp_path)

    result = resolve_runtime_profile(
        app_dir,
        repo_root=tmp_path,
        env={"YIME_RUNTIME_PROFILE": "research_full"},
        is_frozen=False,
    )
    assert result.database_path == tmp_path / "yime/pinyin_hanzi.db"

    with pytest.raises(ValueError, match="不允许进入 portable"):
        resolve_runtime_profile(
            app_dir,
            repo_root=tmp_path,
            env={"YIME_RUNTIME_PROFILE": "research_full"},
            is_frozen=True,
        )


def test_frozen_runtime_uses_packaged_parity_database(tmp_path: Path) -> None:
    app_dir = tmp_path / "yime"
    app_dir.mkdir()
    _write_profile(tmp_path)

    result = resolve_runtime_profile(
        app_dir,
        repo_root=tmp_path,
        env={},
        is_frozen=True,
    )

    assert result.database_path == tmp_path / "yime/pinyin_hanzi.db"
    assert result.manifest_path == (
        tmp_path / "yime/prototype_runtime_manifest.json"
    )


def test_explicit_database_override_keeps_diagnostic_escape_hatch(
    tmp_path: Path,
) -> None:
    app_dir = tmp_path / "yime"
    app_dir.mkdir()
    result = resolve_runtime_profile(
        app_dir,
        repo_root=tmp_path,
        env={"YIME_RUNTIME_DB_PATH": str(tmp_path / "fixture.db")},
        is_frozen=False,
    )
    assert result.profile_id == "explicit_database"
    assert result.is_explicit_database_override is True
    assert result.database_path == (tmp_path / "fixture.db").resolve()


def test_windows_parity_can_require_sqlite_without_json_fallback(
    tmp_path: Path,
) -> None:
    app_dir = tmp_path / "yime"
    app_dir.mkdir()

    with pytest.raises(RuntimeError, match="要求使用 SQLite 运行库"):
        CompositeCandidateDecoder(
            app_dir,
            runtime_db_path=tmp_path / "missing.db",
            require_sqlite_runtime=True,
        )
