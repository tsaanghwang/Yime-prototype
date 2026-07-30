import json
import shutil
import sqlite3
from pathlib import Path

from yime.utils.layout_workbench import (
    LayoutDraft,
    format_trial_result,
    inspect_lexicon,
    probe_lexicon_link,
)
from yime.utils.yinyuan_id_chain import encode_numeric_pinyin_to_yinyuan_ids


ROOT = Path(__file__).resolve().parents[2]


def _draft(repo_root: Path = ROOT) -> LayoutDraft:
    payload = json.loads(
        (repo_root / "internal_data" / "manual_key_layout.json").read_text(encoding="utf-8")
    )
    return LayoutDraft(payload, repo_root)


def _create_workbench_fixture(repo_root: Path) -> None:
    for relative in (
        Path("internal_data/key_to_symbol.json"),
        Path("internal_data/manual_key_layout.json"),
        Path("syllable/yinyuan/zaoyin_yinyuan_enhanced.json"),
        Path("syllable/yinyuan/yueyin_yinyuan_enhanced.json"),
    ):
        destination = repo_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)

    symbols = json.loads(
        (repo_root / "internal_data" / "key_to_symbol.json").read_text(encoding="utf-8")
    )
    canonical_code = "".join(
        symbols[yinyuan_id]
        for yinyuan_id in encode_numeric_pinyin_to_yinyuan_ids("ba1")
    )
    db_path = repo_root / "yime" / "pinyin_hanzi.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE runtime_candidates_materialized (
                text TEXT NOT NULL,
                pinyin_tone TEXT NOT NULL,
                yime_code TEXT NOT NULL,
                entry_type TEXT NOT NULL,
                text_length INTEGER NOT NULL,
                sort_weight REAL NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO runtime_candidates_materialized
                (text, pinyin_tone, yime_code, entry_type, text_length, sort_weight)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("八", "ba1", canonical_code, "char", 1, 1.0),
        )


def test_current_layout_is_accepted() -> None:
    assert _draft().validate().accepted


def test_assignment_swaps_existing_ids_without_losing_coverage() -> None:
    draft = _draft()
    n01_slot = next(entry for entry in draft.layers if entry.get("yinyuan_id") == "N01")
    n10_slot = next(entry for entry in draft.layers if entry.get("yinyuan_id") == "N10")

    draft.assign(int(n01_slot["order"]), "N10")

    assert n01_slot["yinyuan_id"] == "N10"
    assert n10_slot["yinyuan_id"] == "N01"
    assert draft.validate().accepted


def test_candidate_selection_keys_are_locked() -> None:
    draft = _draft()
    shift_one = next(entry for entry in draft.layers if entry.get("display_label") == "!")
    assert draft.is_locked(shift_one)

    try:
        draft.assign(int(shift_one["order"]), "N01")
    except ValueError as exc:
        assert "受布局锁保护" in str(exc)
    else:
        raise AssertionError("Shift+1 must stay reserved for candidate selection")


def test_trial_uses_draft_mapping_before_writing_layout() -> None:
    draft = _draft()
    ids, unknown = draft.trial_ids("bj")
    assert ids == ("N01", "M01")
    assert unknown == ()

    result = draft.trial("bj")
    display = format_trial_result(draft, result)
    assert "N01" in display
    assert "M01" in display


def test_workbench_reports_and_queries_current_lexicon(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _create_workbench_fixture(repo_root)

    status = inspect_lexicon(repo_root / "yime" / "pinyin_hanzi.db")
    assert status.connected
    assert status.row_count == 1
    assert status.code_column == "yime_code"

    draft = _draft(repo_root)
    id_to_token = {yinyuan_id: token for token, yinyuan_id in draft.token_to_id().items()}
    typed = "".join(
        id_to_token[yinyuan_id]
        for yinyuan_id in encode_numeric_pinyin_to_yinyuan_ids("ba1")
    )
    result = draft.trial(typed)
    assert result.candidates
    assert result.query_codepoints
    probe = probe_lexicon_link(draft)
    assert probe.linked
    assert probe.typed_keys == typed
    assert probe.candidate_count > 0


def test_clearing_an_id_blocks_acceptance() -> None:
    draft = _draft()
    n01_slot = next(entry for entry in draft.layers if entry.get("yinyuan_id") == "N01")
    draft.assign(int(n01_slot["order"]), None)
    validation = draft.validate()
    assert not validation.accepted
    assert any("N01" in issue for issue in validation.issues)
