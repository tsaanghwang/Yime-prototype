from __future__ import annotations

from yime.input_method.ui.candidate_box_actions import CandidateBoxActions


class _FakeCandidateBox:
    def __init__(self) -> None:
        self.current_candidates = ["魔高"]
        self.commit_text = ""
        self.committed: list[str] = []
        self.selected: list[str] = []
        self.status = ""

    def get_candidate(self, index: int) -> str | None:
        if 0 <= index < len(self.current_candidates):
            return self.current_candidates[index]
        return None

    def is_manual_input_enabled(self) -> bool:
        return True

    def append_commit_text(self, text: str) -> None:
        self.commit_text += text

    def on_select(self, text: str) -> None:
        self.selected.append(text)

    def clear_input(self, focus_input: bool = True) -> None:
        self.current_candidates = []

    def set_status(self, text: str) -> None:
        self.status = text

    def get_commit_text(self) -> str:
        return self.commit_text

    def commit_text_callback(self, text: str) -> bool:
        self.committed.append(text)
        return True


def test_mouse_clicks_accumulate_segments_until_explicit_commit() -> None:
    box = _FakeCandidateBox()
    actions = CandidateBoxActions(box)

    actions.on_candidate_click(0)
    assert box.commit_text == "魔高"
    assert box.selected == ["魔高"]
    assert box.committed == []

    box.current_candidates = ["一尺"]
    actions.on_candidate_click(0)
    assert box.commit_text == "魔高一尺"
    assert box.selected == ["魔高", "一尺"]
    assert box.committed == []

    actions.commit_output_text()
    assert box.committed == ["魔高一尺"]
