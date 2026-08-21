"""Resolve the prototype runtime database without blurring release and research roles."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping


DEFAULT_PROFILE = "windows_parity"
PROFILE_CONFIG = Path("internal_data/prototype_runtime_profile.json")


@dataclass(frozen=True)
class ResolvedRuntimeProfile:
    profile_id: str
    database_path: Path
    manifest_path: Path | None
    windows_schema: str
    is_explicit_database_override: bool = False


def _load_profile_config(repo_root: Path) -> dict[str, object]:
    path = repo_root / PROFILE_CONFIG
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_runtime_profile(
    app_dir: Path,
    *,
    repo_root: Path | None = None,
    env: Mapping[str, str] | None = None,
    is_frozen: bool = False,
) -> ResolvedRuntimeProfile:
    environment = {} if env is None else env
    resolved_repo_root = repo_root or app_dir.parent
    database_override = str(
        environment.get("YIME_RUNTIME_DB_PATH") or ""
    ).strip()
    if database_override:
        return ResolvedRuntimeProfile(
            profile_id="explicit_database",
            database_path=Path(database_override).expanduser().resolve(),
            manifest_path=None,
            windows_schema="",
            is_explicit_database_override=True,
        )

    payload = _load_profile_config(resolved_repo_root)
    profiles = payload.get("profiles")
    if not isinstance(profiles, dict):
        return ResolvedRuntimeProfile(
            profile_id="legacy_local",
            database_path=app_dir / "pinyin_hanzi.db",
            manifest_path=None,
            windows_schema="",
        )

    requested = str(
        environment.get("YIME_RUNTIME_PROFILE")
        or payload.get("default_profile")
        or DEFAULT_PROFILE
    ).strip()
    profile = profiles.get(requested)
    if not isinstance(profile, dict):
        raise ValueError(f"未知的原型运行 profile: {requested}")

    if is_frozen:
        packaged_database = str(profile.get("packaged_database") or "").strip()
        if not packaged_database:
            raise ValueError(
                f"运行 profile {requested} 不允许进入 portable/安装包"
            )
        database_path = resolved_repo_root / packaged_database
        manifest_path = database_path.with_name("prototype_runtime_manifest.json")
    else:
        source_database = str(profile.get("source_database") or "").strip()
        if not source_database:
            raise ValueError(f"运行 profile {requested} 缺少 source_database")
        database_path = resolved_repo_root / source_database
        manifest_value = str(profile.get("manifest") or "").strip()
        manifest_path = (
            resolved_repo_root / manifest_value if manifest_value else None
        )

    return ResolvedRuntimeProfile(
        profile_id=requested,
        database_path=database_path,
        manifest_path=manifest_path,
        windows_schema=str(profile.get("windows_schema") or ""),
    )
