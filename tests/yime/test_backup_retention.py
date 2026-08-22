from __future__ import annotations

from pathlib import Path

import pytest

from yime.utils import backup as backup_module
from yime.utils.blcu_word_frequency_import import (
    DEFAULT_BACKUP_RETAIN_COUNT as BLCU_BACKUP_RETAIN_COUNT,
)
from yime.utils.runtime_codes_refresh import (
    DEFAULT_BACKUP_RETAIN_COUNT as RUNTIME_BACKUP_RETAIN_COUNT,
)


class _SequencedDatetime:
    stamps = iter(("20260822_100000", "20260822_100001"))

    @classmethod
    def now(cls) -> _SequencedDatetime:
        return cls()

    def strftime(self, _format: str) -> str:
        return next(self.stamps)


def test_timestamped_backup_keeps_only_latest_and_removes_sidecars(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "pinyin_hanzi.db"
    backup_dir = tmp_path / "backup"
    source.write_bytes(b"first")
    monkeypatch.setattr(backup_module, "datetime", _SequencedDatetime)

    first, first_removed = backup_module.create_timestamped_backup(
        source,
        backup_dir=backup_dir,
        backup_tag="blcu_word_freq",
        retain_count=1,
    )
    Path(f"{first}-shm").write_bytes(b"shm")
    Path(f"{first}-wal").write_bytes(b"wal")
    source.write_bytes(b"second")
    second, second_removed = backup_module.create_timestamped_backup(
        source,
        backup_dir=backup_dir,
        backup_tag="yime_code_refresh",
        retain_count=1,
    )

    assert first_removed == []
    assert second_removed == [first]
    assert not first.exists()
    assert not Path(f"{first}-shm").exists()
    assert not Path(f"{first}-wal").exists()
    assert second.read_bytes() == b"second"
    assert list(backup_dir.glob("*.bak")) == [second]


def test_backup_retention_cannot_be_disabled_or_increased(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="fixed at exactly one"):
        backup_module.prune_backup_files(tmp_path, "*.bak", retain_count=0)
    with pytest.raises(ValueError, match="fixed at exactly one"):
        backup_module.prune_backup_files(tmp_path, "*.bak", retain_count=2)


def test_database_writers_default_to_one_backup() -> None:
    assert BLCU_BACKUP_RETAIN_COUNT == 1
    assert RUNTIME_BACKUP_RETAIN_COUNT == 1
