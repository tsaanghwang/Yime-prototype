import json
from pathlib import Path

from yime.utils.layout_workbench import (
    LayoutDraft,
    format_trial_result,
    inspect_lexicon,
    probe_lexicon_link,
)
from yime.utils.yinyuan_id_chain import encode_numeric_pinyin_to_yinyuan_ids


ROOT = Path(__file__).resolve().parents[2]


def _draft() -> LayoutDraft:
    payload = json.loads(
        (ROOT / "internal_data" / "manual_key_layout.json").read_text(encoding="utf-8")
    )
    return LayoutDraft(payload, ROOT)


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


def test_workbench_reports_and_queries_current_lexicon() -> None:
    status = inspect_lexicon(ROOT / "yime" / "pinyin_hanzi.db")
    assert status.connected
    assert status.row_count > 400_000
    assert status.code_column == "yime_code"

    draft = _draft()
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
