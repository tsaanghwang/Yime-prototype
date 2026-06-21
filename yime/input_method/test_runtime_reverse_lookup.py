from pathlib import Path

import pytest

from yime.input_method.utils.runtime_reverse_lookup import (
    RuntimeReverseLookup,
    looks_like_hanzi_text,
)


DB_PATH = Path(__file__).resolve().parent.parent / "pinyin_hanzi.db"


def _require_runtime_db() -> None:
    if not DB_PATH.exists():
        pytest.skip("runtime SQLite database is unavailable in this environment")


def test_looks_like_hanzi_text_detects_plain_hanzi() -> None:
    assert looks_like_hanzi_text("日本") is True
    assert looks_like_hanzi_text("ri4") is False


def test_looks_like_hanzi_text_accepts_extension_plane_hanzi() -> None:
    assert looks_like_hanzi_text("\U00030000") is True
    assert looks_like_hanzi_text("\U00031350") is True


def test_runtime_reverse_lookup_returns_first_char_record() -> None:
    _require_runtime_db()
    lookup = RuntimeReverseLookup(DB_PATH)

    record = lookup.lookup_first("日")

    assert record is not None
    assert record.text == "日"
    assert record.numeric_pinyin == "ri4"
    assert record.marked_pinyin == "rì"
    assert record.yime_code


def test_runtime_reverse_lookup_returns_extension_plane_char_record() -> None:
    _require_runtime_db()
    lookup = RuntimeReverseLookup(DB_PATH)

    record = lookup.lookup_first("𰀡")

    assert record is not None
    assert record.text == "𰀡"
    assert record.numeric_pinyin == "qian1"
    assert record.marked_pinyin == "qiān"
    assert record.yime_code


def test_runtime_reverse_lookup_returns_none_for_missing_phrase() -> None:
    _require_runtime_db()
    lookup = RuntimeReverseLookup(DB_PATH)

    assert lookup.lookup_first("今日不存在") is None


def test_require_runtime_db_skips_when_runtime_db_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_db_path = DB_PATH.parent / "pinyin_hanzi.absent.db"
    monkeypatch.setattr(
        "yime.input_method.test_runtime_reverse_lookup.DB_PATH",
        missing_db_path,
    )

    with pytest.raises(pytest.skip.Exception, match="runtime SQLite database is unavailable"):
        _require_runtime_db()
