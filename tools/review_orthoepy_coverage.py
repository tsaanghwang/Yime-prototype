#!/usr/bin/env python3
"""Visual workbench for orthoepy candidate-coverage additions."""

from __future__ import annotations

import argparse
import json
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from yime.lexicon_bundle.orthoepy_coverage import (  # noqa: E402
    CoverageReviewStore,
    ReviewItem,
    export_approved_catalog,
)


DEFAULT_DIR = ROOT / ".generated" / "orthoepy_coverage"
DEFAULT_AUDIT = DEFAULT_DIR / "orthoepy_coverage.sqlite3"
DEFAULT_CATALOG = (
    ROOT / "internal_data" / "pinyin_source_db" / "orthoepy_coverage_readings.json"
)
DEFAULT_INVENTORY = ROOT / "yime" / "pinyin_normalized.json"


AUTHORITY_LABELS = {
    "全部": "",
    "1985正式表": "official_1985",
    "2016修订稿": "draft_2016",
}
KIND_LABELS = {"全部": "", "单字读音": "single_char", "例词": "example_phrase"}
STATE_LABELS = {
    "待处理": "pending",
    "全部缺口": "all",
    "自动准入": "automatic",
    "已批准": "approved",
    "暂缓": "defer",
    "已拒绝": "reject",
    "失效决定": "stale",
}


class ReviewApplication:
    def __init__(
        self,
        store: CoverageReviewStore,
        *,
        catalog: Path,
        inventory: Path,
        smoke_test: bool = False,
    ) -> None:
        self.store = store
        self.catalog = catalog
        self.inventory = inventory
        self.root = tk.Tk()
        self.root.title("审音表字词读音覆盖补全")
        self.root.geometry("1380x860")
        self.root.minsize(1080, 680)
        self.items: list[ReviewItem] = []
        self.visible: list[ReviewItem] = []
        self.current_key = ""

        self.authority_var = tk.StringVar(value="1985正式表")
        self.kind_var = tk.StringVar(value="全部")
        self.state_var = tk.StringVar(value="待处理")
        self.search_var = tk.StringVar()
        self.corrected_text_var = tk.StringVar()
        self.corrected_pinyin_var = tk.StringVar()
        self.status_var = tk.StringVar()
        self._build_ui()
        self.reload()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        if smoke_test:
            self.root.after(250, self.close)

    def _build_ui(self) -> None:
        controls = ttk.Frame(self.root, padding=8)
        controls.pack(fill="x")
        for label, variable, values in (
            ("证据：", self.authority_var, tuple(AUTHORITY_LABELS)),
            ("类型：", self.kind_var, tuple(KIND_LABELS)),
            ("状态：", self.state_var, tuple(STATE_LABELS)),
        ):
            ttk.Label(controls, text=label).pack(side="left")
            combo = ttk.Combobox(controls, textvariable=variable, values=values, width=12, state="readonly")
            combo.pack(side="left", padx=(0, 8))
            combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh())
        ttk.Label(controls, text="搜索：").pack(side="left")
        search = ttk.Entry(controls, textvariable=self.search_var, width=24)
        search.pack(side="left", padx=(0, 8))
        search.bind("<KeyRelease>", lambda _event: self.refresh())
        ttk.Button(controls, text="刷新", command=self.reload).pack(side="left")
        ttk.Button(controls, text="导出已批准项", command=self.export_catalog).pack(side="right")

        body = ttk.Panedwindow(self.root, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        left = ttk.Frame(body)
        right = ttk.Frame(body, padding=(8, 0, 0, 0))
        body.add(left, weight=3)
        body.add(right, weight=4)

        columns = ("state", "authority", "kind", "text", "target", "proposal", "page")
        self.tree = ttk.Treeview(left, columns=columns, show="headings", selectmode="browse")
        headings = {
            "state": "状态",
            "authority": "证据",
            "kind": "类型",
            "text": "词形",
            "target": "目标字音",
            "proposal": "拟增完整拼音",
            "page": "页/行",
        }
        widths = {"state": 85, "authority": 90, "kind": 75, "text": 130, "target": 90, "proposal": 210, "page": 80}
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], anchor="w")
        scrollbar = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._select)

        self.detail = tk.Text(right, wrap="word", height=23, font=("Microsoft YaHei UI", 11))
        self.detail.pack(fill="both", expand=True)
        editor = ttk.LabelFrame(right, text="校正后新增项（只有“校正并批准”使用这里）", padding=8)
        editor.pack(fill="x", pady=(8, 0))
        ttk.Label(editor, text="词形：").grid(row=0, column=0, sticky="w")
        ttk.Entry(editor, textvariable=self.corrected_text_var).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Label(editor, text="完整拼音：").grid(row=1, column=0, sticky="w")
        ttk.Entry(editor, textvariable=self.corrected_pinyin_var).grid(row=1, column=1, sticky="ew", padx=6, pady=(5, 0))
        ttk.Label(editor, text="备注：").grid(row=2, column=0, sticky="nw", pady=(5, 0))
        self.note = tk.Text(editor, height=3, wrap="word")
        self.note.grid(row=2, column=1, sticky="ew", padx=6, pady=(5, 0))
        editor.columnconfigure(1, weight=1)

        actions = ttk.Frame(right, padding=(0, 8, 0, 0))
        actions.pack(fill="x")
        ttk.Button(actions, text="批准拟增项", command=lambda: self.save("approve")).pack(side="left")
        ttk.Button(actions, text="校正并批准", command=lambda: self.save("corrected_approve")).pack(side="left", padx=6)
        ttk.Button(actions, text="暂缓", command=lambda: self.save("defer")).pack(side="left")
        ttk.Button(actions, text="拒绝", command=lambda: self.save("reject")).pack(side="left", padx=6)
        ttk.Button(actions, text="撤销决定", command=self.clear).pack(side="left")
        ttk.Label(actions, textvariable=self.status_var).pack(side="right")

    @staticmethod
    def _state(item: ReviewItem) -> str:
        if item.stale_decision:
            return "失效"
        if item.decision == "pending" and item.candidate.auto_eligible:
            return "自动准入"
        return {
            "pending": "待处理",
            "approve": "已批准",
            "corrected_approve": "校正批准",
            "defer": "暂缓",
            "reject": "拒绝",
        }[item.decision]

    def reload(self) -> None:
        self.items = self.store.load_items()
        self.refresh()

    def _matches(self, item: ReviewItem) -> bool:
        candidate = item.candidate
        authority = AUTHORITY_LABELS[self.authority_var.get()]
        kind = KIND_LABELS[self.kind_var.get()]
        if authority and candidate.version_key != authority:
            return False
        if kind and candidate.candidate_kind != kind:
            return False
        state = STATE_LABELS[self.state_var.get()]
        if state == "pending" and not (item.decision == "pending" and not candidate.auto_eligible):
            return False
        if state == "automatic" and not candidate.auto_eligible:
            return False
        if state == "approved" and item.decision not in {"approve", "corrected_approve"}:
            return False
        if state in {"defer", "reject"} and item.decision != state:
            return False
        if state == "stale" and not item.stale_decision:
            return False
        search = self.search_var.get().strip().lower()
        return not search or search in (candidate.text + candidate.source_entry_text + candidate.proposed_marked_pinyin).lower()

    def refresh(self, preferred_key: str = "") -> None:
        self.visible = [item for item in self.items if self._matches(item)]
        self.tree.delete(*self.tree.get_children())
        for item in self.visible:
            candidate = item.candidate
            self.tree.insert(
                "",
                "end",
                iid=candidate.candidate_key,
                values=(
                    self._state(item),
                    "1985正式" if candidate.version_key == "official_1985" else "2016草案",
                    "单字" if candidate.candidate_kind == "single_char" else "例词",
                    candidate.text,
                    candidate.target_reading,
                    candidate.proposed_marked_pinyin or " / ".join(candidate.proposal_options),
                    f"{candidate.word_page_number}/{candidate.source_row}",
                ),
            )
        keys = [item.candidate.candidate_key for item in self.visible]
        key = preferred_key if preferred_key in keys else (keys[0] if keys else "")
        if key:
            self.tree.selection_set(key)
            self.tree.focus(key)
            self.tree.see(key)
            self.show(next(item for item in self.visible if item.candidate.candidate_key == key))
        else:
            self.current_key = ""
            self.detail.delete("1.0", "end")
        self.status_var.set(f"当前 {len(self.visible)} / 全部缺口 {len(self.items)}")

    def _select(self, _event: object = None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        key = selection[0]
        self.show(next(item for item in self.visible if item.candidate.candidate_key == key))

    def show(self, item: ReviewItem) -> None:
        candidate = item.candidate
        self.current_key = candidate.candidate_key
        self.corrected_text_var.set(item.corrected_text or candidate.text)
        self.corrected_pinyin_var.set(item.corrected_pinyin or candidate.proposed_marked_pinyin)
        self.note.delete("1.0", "end")
        self.note.insert("1.0", item.note)
        lines = [
            f"证据版本：{'1985 正式表' if candidate.version_key == 'official_1985' else '2016 修订稿（征求意见）'}",
            f"位置：第 {candidate.word_page_number} 页，表格第 {candidate.source_row} 行，{candidate.section_label} 部",
            f"候选类型：{candidate.candidate_kind}",
            f"词形：{candidate.text}",
            f"审音表目标字音：{candidate.target_reading}  [{candidate.target_numeric}]",
            f"拟增完整拼音：{candidate.proposed_marked_pinyin or '尚未唯一确定'}",
            f"数字拼音：{candidate.proposed_numeric_pinyin}",
            f"其他方案：{' / '.join(candidate.proposal_options)}",
            f"覆盖状态：{candidate.coverage_status}",
            f"生成依据：{candidate.derivation}",
            f"现有门禁：{'通过' if candidate.gate_accepted else candidate.gate_reason or '未运行'}",
            f"说明：{candidate.explanation}",
            f"当前决定：{self._state(item)}",
            "",
            "审音表原条目：",
            candidate.source_entry_text,
        ]
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", "\n".join(lines))

    def _next_key(self) -> str:
        keys = [item.candidate.candidate_key for item in self.visible]
        if self.current_key not in keys or len(keys) < 2:
            return ""
        return keys[(keys.index(self.current_key) + 1) % len(keys)]

    def save(self, decision: str) -> None:
        if not self.current_key:
            return
        next_key = self._next_key()
        try:
            self.store.save(
                self.current_key,
                decision,
                corrected_text=self.corrected_text_var.get(),
                corrected_pinyin=self.corrected_pinyin_var.get(),
                note=self.note.get("1.0", "end").strip(),
            )
        except Exception as error:
            messagebox.showerror("保存失败", str(error), parent=self.root)
            return
        self.items = self.store.load_items()
        self.refresh(next_key)

    def clear(self) -> None:
        if self.current_key:
            self.store.clear(self.current_key)
            self.items = self.store.load_items()
            self.refresh(self.current_key)

    def export_catalog(self) -> None:
        try:
            result = export_approved_catalog(
                self.store, self.catalog, decoder_inventory=self.inventory
            )
        except Exception as error:
            messagebox.showerror("导出失败", str(error), parent=self.root)
            return
        messagebox.showinfo(
            "导出完成",
            f"已写入 {result['record_count']} 条；门禁拒绝 {result['rejected_count']} 条。\n{result['output']}",
            parent=self.root,
        )

    def close(self) -> None:
        self.store.close()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--decision-database", type=Path)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--decoder-inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--smoke-test", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    store = CoverageReviewStore(args.database, args.decision_database)
    app = ReviewApplication(
        store,
        catalog=args.catalog,
        inventory=args.decoder_inventory,
        smoke_test=args.smoke_test,
    )
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
