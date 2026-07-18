"""Visual, reversible keyboard-layout trial workbench."""

from __future__ import annotations

import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from yime.utils.layout_workbench import (
    LayoutDraft,
    format_trial_result,
    inspect_lexicon,
    probe_lexicon_link,
    write_canonical_layout_atomic,
)


ROW_KEYS = {
    "number": list("`1234567890-="),
    "top": list("qwertyuiop[]\\"),
    "home": list("asdfghjkl;'"),
    "bottom": list("zxcvbnm,./"),
}
ROW_PAD = {"number": 0, "top": 18, "home": 34, "bottom": 56}


class LayoutWorkbench:
    def __init__(self, root: tk.Tk, repo_root: Path = ROOT) -> None:
        self.root = root
        self.repo_root = repo_root
        self.layout_path = repo_root / "internal_data" / "manual_key_layout.json"
        self.original_text = self.layout_path.read_text(encoding="utf-8")
        self.draft = LayoutDraft.load(repo_root)
        self.selected_order: int | None = None
        self.buttons: dict[int, ttk.Button] = {}

        root.title("Yime 布局试验工作台")
        root.geometry("1240x820")
        root.minsize(980, 680)
        self._build()
        self.refresh_all()

    def _build(self) -> None:
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill="both", expand=True)

        ttk.Label(
            outer,
            text="试验只保存在内存；合格后点击“接受并生成”，失败会自动恢复正式布局。",
        ).pack(anchor="w")

        notebook = ttk.Notebook(outer)
        notebook.pack(fill="x", pady=(10, 6))
        for layer, title in (("base", "Base 层"), ("shift", "Shift 层")):
            frame = ttk.Frame(notebook, padding=10)
            notebook.add(frame, text=title)
            self._build_keyboard(frame, layer)

        editor = ttk.LabelFrame(outer, text="所选键位", padding=10)
        editor.pack(fill="x", pady=6)
        self.slot_text = tk.StringVar(value="请在上方选择一个键位")
        ttk.Label(editor, textvariable=self.slot_text, width=42).grid(row=0, column=0, sticky="w")
        self.id_value = tk.StringVar()
        values = [""] + sorted(self.draft.registry)
        self.id_combo = ttk.Combobox(
            editor,
            textvariable=self.id_value,
            values=values,
            state="readonly",
            width=12,
        )
        self.id_combo.grid(row=0, column=1, padx=8)
        self.id_combo.bind("<<ComboboxSelected>>", self.apply_assignment)
        ttk.Label(editor, text="选择后立即交换并进入试打草案").grid(
            row=0, column=2, padx=4
        )
        ttk.Button(editor, text="放弃本轮，恢复正式布局", command=self.reset).grid(
            row=0, column=3, padx=4
        )

        trial = ttk.LabelFrame(outer, text="试打（按当前草案查原型词库）", padding=10)
        trial.pack(fill="both", expand=True, pady=6)
        self.lexicon_status = inspect_lexicon(self.repo_root / "yime" / "pinyin_hanzi.db")
        ttk.Label(trial, text=self.lexicon_status.display).pack(anchor="w")
        self.lexicon_probe_text = tk.StringVar()
        ttk.Label(trial, textvariable=self.lexicon_probe_text).pack(anchor="w", pady=(2, 6))
        self.trial_text = tk.StringVar()
        trial_entry = ttk.Entry(trial, textvariable=self.trial_text, font=("Consolas", 14))
        trial_entry.pack(fill="x")
        trial_entry.bind("<KeyRelease>", lambda _event: self.update_trial())
        self.trial_output = tk.Text(trial, height=9, wrap="word", state="disabled")
        self.trial_output.pack(fill="both", expand=True, pady=(8, 0))

        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(8, 0))
        self.status_text = tk.StringVar()
        ttk.Label(footer, textvariable=self.status_text).pack(side="left", fill="x", expand=True)
        self.accept_button = ttk.Button(
            footer,
            text="保存布局并进入生成流程",
            command=self.accept,
        )
        self.accept_button.pack(side="right")

    def _build_keyboard(self, parent: ttk.Frame, layer: str) -> None:
        entries = {
            (str(entry.get("physical_key")), str(entry.get("output_layer"))): entry
            for entry in self.draft.layers
        }
        for row_index, (row_name, keys) in enumerate(ROW_KEYS.items()):
            row = ttk.Frame(parent)
            row.pack(anchor="w", padx=ROW_PAD[row_name], pady=2)
            for key in keys:
                entry = entries.get((key, layer))
                if entry is None:
                    continue
                order = int(entry["order"])
                button = ttk.Button(
                    row,
                    width=10,
                    command=lambda selected=order: self.select_slot(selected),
                )
                button.pack(side="left", padx=2)
                self.buttons[order] = button

    def _button_text(self, entry: dict[str, object]) -> str:
        key = str(entry.get("display_label") or entry.get("physical_key") or "")
        yinyuan_id = str(entry.get("yinyuan_id") or "")
        if yinyuan_id:
            label = self.draft.registry[yinyuan_id]["label"]
            return f"{key}\n{yinyuan_id} {label}"
        if self.draft.is_locked(entry):
            return f"{key}\n〔保留〕"
        return f"{key}\n—"

    def select_slot(self, order: int) -> None:
        entry = self.draft.slot(order)
        self.selected_order = order
        layer = str(entry.get("output_layer") or "")
        label = str(entry.get("display_label") or "")
        locked = self.draft.is_locked(entry)
        self.slot_text.set(f"键位：{label}（{layer}）" + ("；受保护" if locked else ""))
        self.id_value.set(str(entry.get("yinyuan_id") or ""))
        self.id_combo.configure(state="disabled" if locked else "readonly")

    def apply_assignment(self, _event: object | None = None) -> None:
        if self.selected_order is None:
            messagebox.showinfo("布局试验", "请先选择一个键位。", parent=self.root)
            return
        value = self.id_value.get().strip() or None
        try:
            self.draft.assign(self.selected_order, value)
        except ValueError as exc:
            messagebox.showerror("不能分配", str(exc), parent=self.root)
            return
        self.refresh_all()
        self.select_slot(self.selected_order)

    def reset(self) -> None:
        if not messagebox.askyesno("恢复布局", "放弃尚未接受的改动？", parent=self.root):
            return
        self.draft = LayoutDraft.load(self.repo_root)
        self.original_text = self.layout_path.read_text(encoding="utf-8")
        self.selected_order = None
        self.slot_text.set("请在上方选择一个键位")
        self.id_value.set("")
        self.refresh_all()

    def refresh_all(self) -> None:
        for order, button in self.buttons.items():
            button.configure(text=self._button_text(self.draft.slot(order)))
        validation = self.draft.validate()
        if validation.accepted:
            self.status_text.set("✓ 草案结构合格；可以继续试打或保存布局。")
            self.accept_button.configure(state="normal")
        else:
            self.status_text.set("✗ " + "；".join(validation.issues[:3]))
            self.accept_button.configure(state="disabled")
        self.lexicon_probe_text.set(probe_lexicon_link(self.draft).display)
        self.update_trial()

    def update_trial(self) -> None:
        result = self.draft.trial(self.trial_text.get())
        output = format_trial_result(self.draft, result)
        self.trial_output.configure(state="normal")
        self.trial_output.delete("1.0", "end")
        self.trial_output.insert("1.0", output)
        self.trial_output.configure(state="disabled")

    def accept(self) -> None:
        validation = self.draft.validate()
        if not validation.accepted:
            messagebox.showerror("布局不合格", "\n".join(validation.issues), parent=self.root)
            return
        if self.layout_path.read_text(encoding="utf-8") != self.original_text:
            messagebox.showwarning(
                "正式布局已在外部改变",
                "为避免覆盖其他修改，本次草案没有写入。请恢复正式布局后重新试验。",
                parent=self.root,
            )
            return
        if not messagebox.askyesno(
            "保存布局",
            "保存后立即生效，并自动进入完整锁定生成流程。继续吗？",
            parent=self.root,
        ):
            return

        candidate_text = self.draft.serialized()
        self.accept_button.configure(state="disabled")
        self.status_text.set("正在运行锁定生成链……")
        self.root.update_idletasks()
        try:
            write_canonical_layout_atomic(self.repo_root, candidate_text)
            result = subprocess.run(
                [sys.executable, str(self.repo_root / "tools" / "run_locked_layout_pipeline.py")],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError((result.stdout + "\n" + result.stderr).strip())
        except Exception as exc:
            write_canonical_layout_atomic(self.repo_root, self.original_text)
            subprocess.run(
                [sys.executable, str(self.repo_root / "tools" / "run_locked_layout_pipeline.py")],
                cwd=self.repo_root,
                capture_output=True,
                check=False,
            )
            self.status_text.set("✗ 保存失败，已自动恢复原布局。")
            self.accept_button.configure(state="normal")
            messagebox.showerror("保存失败，已恢复", str(exc), parent=self.root)
            return

        self.original_text = candidate_text
        self.draft = LayoutDraft.load(self.repo_root)
        self.refresh_all()
        messagebox.showinfo("布局已保存", "正式布局已生效，锁定生成流程已经完成。", parent=self.root)


def main() -> int:
    root = tk.Tk()
    LayoutWorkbench(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
