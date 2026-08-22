from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path


def prune_backup_files(
    backup_dir: Path,
    pattern: str,
    retain_count: int,
    *,
    keep_path: Path | None = None,
) -> list[Path]:
    if retain_count != 1:
        raise ValueError("backup retention is fixed at exactly one file")

    backups = sorted(
        backup_dir.glob(pattern),
        key=lambda path: (path.stat().st_mtime_ns, path.name),
        reverse=True,
    )
    if keep_path is None:
        stale_backups = backups[retain_count:]
    else:
        stale_backups = [path for path in backups if path != keep_path]
    removed: list[Path] = []
    for path in stale_backups:
        path.unlink(missing_ok=True)
        removed.append(path)
        for suffix in ("-shm", "-wal"):
            Path(f"{path}{suffix}").unlink(missing_ok=True)
    return removed


def create_timestamped_backup(
    db_path: Path,
    *,
    backup_dir: Path,
    backup_tag: str,
    retain_count: int,
) -> tuple[Path, list[Path]]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"{db_path.stem}.{backup_tag}_{timestamp}.bak"
    shutil.copy2(db_path, backup_path)
    removed = prune_backup_files(
        backup_dir,
        f"{db_path.stem}.*.bak",
        retain_count,
        keep_path=backup_path,
    )
    return backup_path, removed
