#!/usr/bin/env python3
"""Visual three-segment quality review for the research-only erhua draft."""

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

from syllable.analysis.erhua_final_review import (  # noqa: E402
    SEGMENT_NAMES,
    ErhuaFinalDraftStore,
    ErhuaReviewItem,
    render_surface_segments,
)


DEFAULT_DRAFT = ROOT / "external_data" / "tmp" / "final_styles_erhua_draft.json"
DEFAULT_DECOMPOSITION = (
    ROOT
    / "internal_data"
    / "yinyuan_derived"
    / "ganyin_to_pianyin_sequence.json"
)

STATE_FILTERS = {
    "全部": "all",
    "待标注": "pending",
    "已标注": "reviewed",
    "暂缓": "deferred",
    "不适用": "not_applicable",
    "来源疑点": "source_discrepancy",
}
STATE_LABELS = {
    "pending": "待标注",
    "reviewed": "已标注",
    "deferred": "暂缓",
    "not_applicable": "不适用",
}


class ReviewApplication:
    def __init__(self, store: ErhuaFinalDraftStore) -> None:
        self.store = store
        self.root = tk.Tk()
        self.root.title("儿化韵三段音质复核器（研究草稿）")
        self.root.geometry("1520x920")
        self.root.minsize(1180, 720)

        self.items: list[ErhuaReviewItem] = []
        self.visible: list[ErhuaReviewItem] = []
        self.item_by_final: dict[str, ErhuaReviewItem] = {}
        self.current_final = ""
        self._loading = False
        self._dirty = False

        self.state_var = tk.StringVar(value="待标注")
        self.psc_group_var = tk.StringVar(value="全部结果类")
        self.psc_group_label_to_key: dict[str, str] = {"全部结果类": "all"}
        self.psc_group_order: dict[str, int] = {}
        self.search_var = tk.StringVar()
        self.header_var = tk.StringVar(value="尚未选择韵母")
        self.base_ipa_var = tk.StringVar()
        self.base_segments_var = tk.StringVar()
        self.base_ganyin_var = tk.StringVar()
        self.preview_var = tk.StringVar()
        self.ipa_preview_var = tk.StringVar()
        self.status_var = tk.StringVar()
        self.surface_vars = {name: tk.StringVar() for name in SEGMENT_NAMES}
        self.rhotic_vars = {name: tk.BooleanVar() for name in SEGMENT_NAMES}
        self.nasalized_vars = {name: tk.BooleanVar() for name in SEGMENT_NAMES}

        self._configure_style()
        self._build_ui()
        self._bind_shortcuts()
        self.reload()
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        style.configure(".", font=("Microsoft YaHei UI", 10))
        style.configure("Treeview", rowheight=28, font=("Microsoft YaHei UI", 10))
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("Segment.TEntry", font=("Segoe UI", 14))

    def _build_ui(self) -> None:
        controls = ttk.Frame(self.root, padding=8)
        controls.pack(fill="x")
        ttk.Label(controls, text="状态：").pack(side="left")
        state = ttk.Combobox(
            controls,
            textvariable=self.state_var,
            values=tuple(STATE_FILTERS),
            width=10,
            state="readonly",
        )
        state.pack(side="left", padx=(0, 10))
        state.bind("<<ComboboxSelected>>", lambda _event: self.refresh_with_guard())
        ttk.Label(controls, text="PSC 结果类：").pack(side="left")
        self.psc_group_box = ttk.Combobox(
            controls,
            textvariable=self.psc_group_var,
            values=("全部结果类",),
            width=16,
            state="readonly",
        )
        self.psc_group_box.pack(side="left", padx=(0, 10))
        self.psc_group_box.bind(
            "<<ComboboxSelected>>", lambda _event: self.refresh_with_guard()
        )
        ttk.Label(controls, text="搜索：").pack(side="left")
        search = ttk.Entry(controls, textvariable=self.search_var, width=28)
        search.pack(side="left", padx=(0, 6))
        search.bind("<Return>", lambda _event: self.refresh_with_guard())
        ttk.Button(controls, text="筛选", command=self.refresh_with_guard).pack(side="left")
        ttk.Button(controls, text="重新载入", command=self.reload_with_guard).pack(side="left", padx=6)
        ttk.Label(
            controls,
            text="仅写临时草稿；不生成编码、不接运行时",
            foreground="#9a3412",
        ).pack(side="right")

        body = ttk.Panedwindow(self.root, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        left = ttk.Frame(body)
        right = ttk.Frame(body, padding=(10, 0, 0, 0))
        body.add(left, weight=3)
        body.add(right, weight=5)

        columns = ("state", "psc_group", "final", "ipa", "segments", "category", "rule")
        self.tree = ttk.Treeview(left, columns=columns, show="headings", selectmode="browse")
        headings = {
            "state": "状态",
            "psc_group": "PSC 结果类",
            "final": "韵母",
            "ipa": "基础 IPA",
            "segments": "干音三段音质",
            "category": "现行分类",
            "rule": "PSC 规则",
        }
        widths = {
            "state": 82,
            "psc_group": 105,
            "final": 65,
            "ipa": 90,
            "segments": 145,
            "category": 120,
            "rule": 190,
        }
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], minwidth=55, anchor="w")
        tree_scroll = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._select)

        title = ttk.Frame(right)
        title.pack(fill="x")
        ttk.Label(title, textvariable=self.header_var, font=("Microsoft YaHei UI", 17, "bold")).pack(side="left")
        ttk.Label(title, text="基础整体 IPA：").pack(side="left", padx=(18, 2))
        ttk.Label(title, textvariable=self.base_ipa_var, font=("Segoe UI", 15)).pack(side="left")
        ttk.Label(title, textvariable=self.status_var).pack(side="right")

        base_summary = ttk.Frame(right)
        base_summary.pack(fill="x", pady=(4, 0))
        ttk.Label(base_summary, text="干音三段音质：").pack(side="left")
        ttk.Label(
            base_summary,
            textvariable=self.base_segments_var,
            font=("Segoe UI", 14, "bold"),
        ).pack(side="left")
        ttk.Label(base_summary, text="　提取条目：").pack(side="left")
        ttk.Label(
            base_summary,
            textvariable=self.base_ganyin_var,
            font=("Segoe UI", 12),
        ).pack(side="left")

        source_frame = ttk.LabelFrame(right, text="来源规则、词例与现有 IPA 工作候选", padding=6)
        source_frame.pack(fill="both", expand=True, pady=(8, 0))
        self.source_text = tk.Text(
            source_frame,
            height=15,
            wrap="word",
            font=("Microsoft YaHei UI", 10),
            undo=False,
        )
        source_scroll = ttk.Scrollbar(source_frame, orient="vertical", command=self.source_text.yview)
        self.source_text.configure(yscrollcommand=source_scroll.set)
        self.source_text.pack(side="left", fill="both", expand=True)
        source_scroll.pack(side="right", fill="y")
        self.source_text.configure(state="disabled")

        segment_frame = ttk.LabelFrame(
            right,
            text="三段音质重新标注（音质与并行特征分开保存；˞/ɚ/鼻化符不构成新片音）",
            padding=8,
        )
        segment_frame.pack(fill="x", pady=(8, 0))
        for column, (label, width) in enumerate(
            (("位置", 8), ("现行基础音质", 18), ("儿化后基础音质", 22), ("卷舌", 7), ("鼻化", 7))
        ):
            ttk.Label(segment_frame, text=label, font=("Microsoft YaHei UI", 10, "bold"), width=width).grid(
                row=0, column=column, sticky="w", padx=4, pady=(0, 4)
            )
        self.base_segment_labels: dict[str, ttk.Label] = {}
        for row, name in enumerate(SEGMENT_NAMES, start=1):
            ttk.Label(segment_frame, text=name).grid(row=row, column=0, sticky="w", padx=4, pady=4)
            base_label = ttk.Label(segment_frame, text="", font=("Segoe UI", 14))
            base_label.grid(row=row, column=1, sticky="ew", padx=4, pady=4)
            self.base_segment_labels[name] = base_label
            editor = ttk.Entry(
                segment_frame,
                textvariable=self.surface_vars[name],
                width=22,
                style="Segment.TEntry",
            )
            editor.grid(row=row, column=2, sticky="ew", padx=4, pady=4)
            ttk.Checkbutton(segment_frame, variable=self.rhotic_vars[name]).grid(row=row, column=3, padx=4)
            ttk.Checkbutton(segment_frame, variable=self.nasalized_vars[name]).grid(row=row, column=4, padx=4)
            self.surface_vars[name].trace_add("write", self._editor_changed)
            self.rhotic_vars[name].trace_add("write", self._editor_changed)
            self.nasalized_vars[name].trace_add("write", self._editor_changed)
        segment_frame.columnconfigure(2, weight=1)

        preview = ttk.Frame(segment_frame)
        preview.grid(row=4, column=0, columnspan=5, sticky="ew", pady=(8, 0))
        ttk.Label(preview, text="Yime 上标 r 显示：").pack(side="left")
        ttk.Label(preview, textvariable=self.preview_var, font=("Segoe UI", 15, "bold")).pack(side="left")
        ttk.Label(preview, text="　标准 IPA：").pack(side="left")
        ttk.Label(preview, textvariable=self.ipa_preview_var, font=("Segoe UI", 15)).pack(side="left")
        ttk.Button(preview, text="复制基础三段", command=self.copy_base_segments).pack(side="right")
        ttk.Button(preview, text="清空儿化三段", command=self.clear_surface_segments).pack(side="right", padx=6)

        note_frame = ttk.LabelFrame(right, text="复核备注", padding=6)
        note_frame.pack(fill="x", pady=(8, 0))
        self.note_text = tk.Text(note_frame, height=4, wrap="word", font=("Microsoft YaHei UI", 10))
        self.note_text.pack(fill="x")
        self.note_text.bind("<KeyRelease>", lambda _event: self._mark_dirty())

        actions = ttk.Frame(right, padding=(0, 8, 0, 0))
        actions.pack(fill="x")
        ttk.Button(actions, text="◀ 上一项", command=self.previous).pack(side="left")
        ttk.Button(actions, text="下一项 ▶", command=self.next).pack(side="left", padx=6)
        ttk.Button(actions, text="撤销本项标注", command=self.clear_review).pack(side="left", padx=(8, 0))
        ttk.Button(
            actions,
            text="标为不适用",
            command=lambda: self.save_decision("not_applicable", advance=True),
        ).pack(side="right")
        ttk.Button(
            actions,
            text="暂缓并下一项",
            command=lambda: self.save_decision("deferred", advance=True),
        ).pack(side="right", padx=6)
        ttk.Button(
            actions,
            text="保存并下一项",
            command=lambda: self.save_decision("reviewed", advance=True),
        ).pack(side="right")
        ttk.Button(
            actions,
            text="仅保存",
            command=lambda: self.save_decision("reviewed", advance=False),
        ).pack(side="right", padx=6)

        ttk.Label(
            right,
            text="快捷键：Ctrl+S 仅保存；Ctrl+Enter 保存并下一项；Alt+←/→ 切换。来源内容只读。",
            foreground="#475569",
        ).pack(anchor="w", pady=(4, 0))

    def _bind_shortcuts(self) -> None:
        self.root.bind("<Control-s>", lambda _event: self.save_decision("reviewed", advance=False))
        self.root.bind("<Control-Return>", lambda _event: self.save_decision("reviewed", advance=True))
        self.root.bind("<Alt-Left>", lambda _event: self.previous())
        self.root.bind("<Alt-Right>", lambda _event: self.next())

    def _editor_changed(self, *_args: object) -> None:
        self._update_preview()
        self._mark_dirty()

    def _mark_dirty(self) -> None:
        if not self._loading and self.current_final:
            self._dirty = True

    def _update_preview(self) -> None:
        try:
            segments = self._surface_segments()
            self.preview_var.set(
                render_surface_segments(segments, notation="yime_combining_r")
            )
            self.ipa_preview_var.set(render_surface_segments(segments, notation="ipa"))
        except ValueError as error:
            self.preview_var.set(f"格式错误：{error}")
            self.ipa_preview_var.set("")

    def reload(self, preferred_final: str = "") -> None:
        self.items = self.store.load_items()
        self.item_by_final = {item.final: item for item in self.items}
        groups: list[tuple[str, str, int]] = []
        seen: set[str] = set()
        for item in self.items:
            for group in item.psc_result_groups:
                key = str(group["key"])
                if key in seen:
                    continue
                seen.add(key)
                indices = [
                    int(row.get("source_index"))
                    for row in item.source_annotations
                    if row.get("source_index") is not None
                    and str(row.get("source_erhua_final") or "")
                    == str(group["source_erhua_final"])
                    and bool(row.get("nasalized")) == bool(group["nasalized"])
                ]
                groups.append((str(group["label"]), key, min(indices or [10_000])))
        groups.sort(key=lambda row: (row[2], row[0]))
        self.psc_group_label_to_key = {"全部结果类": "all"}
        self.psc_group_order = {}
        for order, (label, key, _source_index) in enumerate(groups):
            self.psc_group_label_to_key[label] = key
            self.psc_group_order[key] = order
        self.psc_group_label_to_key["无 PSC 对应类别"] = "none"
        self.psc_group_box.configure(values=tuple(self.psc_group_label_to_key))
        if self.psc_group_var.get() not in self.psc_group_label_to_key:
            self.psc_group_var.set("全部结果类")
        self._dirty = False
        self.refresh(preferred_final)

    def reload_with_guard(self) -> None:
        if self._confirm_discard():
            self.reload(self.current_final)

    def _matches(self, item: ErhuaReviewItem) -> bool:
        state = STATE_FILTERS[self.state_var.get()]
        if state == "source_discrepancy":
            if item.source_review_status != "source_discrepancy":
                return False
        elif state != "all" and item.decision != state:
            return False
        group_key = self.psc_group_label_to_key.get(self.psc_group_var.get(), "all")
        if group_key == "none" and item.psc_result_group_keys:
            return False
        if group_key not in {"all", "none"} and group_key not in item.psc_result_group_keys:
            return False
        search = self.search_var.get().strip().lower()
        if not search:
            return True
        examples = " ".join(
            str(example.get("hanzi") or "") + str(example.get("pinyin_nfc") or "")
            for annotation in item.source_annotations
            for example in annotation.get("examples") or []
        )
        haystack = " ".join(
            (
                item.final,
                item.display_final,
                item.base_ipa,
                item.category,
                item.psc_result_group_text,
                item.source_rules,
                examples,
            )
        ).lower()
        return search in haystack

    def refresh_with_guard(self) -> None:
        if self._confirm_discard():
            self.refresh(self.current_final)

    def refresh(self, preferred_final: str = "") -> None:
        self.visible = sorted(
            (item for item in self.items if self._matches(item)),
            key=lambda item: (
                min(
                    (self.psc_group_order.get(key, 10_000) for key in item.psc_result_group_keys),
                    default=10_001,
                ),
                item.final,
            ),
        )
        self.tree.delete(*self.tree.get_children())
        for item in self.visible:
            state = STATE_LABELS[item.decision]
            if item.source_review_status == "source_discrepancy" and item.decision == "pending":
                state = "来源疑点"
            self.tree.insert(
                "",
                "end",
                iid=item.final,
                values=(
                    state,
                    item.psc_result_group_text,
                    item.display_final,
                    item.base_ipa,
                    item.base_segment_text,
                    item.category,
                    item.source_rules or "—",
                ),
            )
        keys = [item.final for item in self.visible]
        target = preferred_final if preferred_final in keys else (keys[0] if keys else "")
        if target:
            self.tree.selection_set(target)
            self.tree.focus(target)
            self.tree.see(target)
            self.show(self.item_by_final[target])
        else:
            self.current_final = ""
            self.header_var.set("筛选结果为空")
            self._set_source_text("")
        counts = {key: 0 for key in STATE_LABELS}
        for item in self.items:
            counts[item.decision] += 1
        self.status_var.set(
            f"显示 {len(self.visible)}/{len(self.items)}；待标注 {counts['pending']}；"
            f"已标注 {counts['reviewed']}；暂缓 {counts['deferred']}；不适用 {counts['not_applicable']}"
        )

    def _select(self, _event: object = None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        final = selection[0]
        if final == self.current_final:
            return
        if not self._confirm_discard():
            if self.current_final:
                self.tree.selection_set(self.current_final)
            return
        self.show(self.item_by_final[final])

    def _set_source_text(self, value: str) -> None:
        self.source_text.configure(state="normal")
        self.source_text.delete("1.0", "end")
        self.source_text.insert("1.0", value)
        self.source_text.configure(state="disabled")

    def show(self, item: ErhuaReviewItem) -> None:
        self._loading = True
        self.current_final = item.final
        self.header_var.set(f"{item.display_final}　[{STATE_LABELS[item.decision]}]")
        self.base_ipa_var.set(item.base_ipa)
        self.base_segments_var.set(item.base_segment_text)
        self.base_ganyin_var.set(item.base_segment_ganyin)
        review = item.review
        surface = review.get("surface_segments") or {}
        for name in SEGMENT_NAMES:
            self.base_segment_labels[name].configure(text=item.base_segments[name])
            segment = surface.get(name) or {}
            features = segment.get("features") or {}
            self.surface_vars[name].set(str(segment.get("quality") or ""))
            self.rhotic_vars[name].set(bool(features.get("rhotic")))
            self.nasalized_vars[name].set(bool(features.get("nasalized")))
        self.note_text.delete("1.0", "end")
        self.note_text.insert("1.0", str(review.get("note") or item.source_note))
        self._set_source_text(self._source_description(item))
        self._update_preview()
        self._loading = False
        self._dirty = False

    @staticmethod
    def _source_description(item: ErhuaReviewItem) -> str:
        lines = [
            f"现行类别：{item.category}",
            f"复核韵母：{item.display_final}    整体 IPA：{item.base_ipa}",
            f"规范内部韵母：{item.canonical_final}",
            f"三段分解查表形式：{item.base_segment_form}",
            f"干音提取条目：{item.base_segment_ganyin} → {item.base_segment_text}",
            f"来源复核状态：{item.source_review_status or '未登记'}",
            f"PSC 结果类：{item.psc_result_group_text}",
        ]
        surface_class = str(item.review.get("surface_class") or "")
        if surface_class:
            lines.append(f"规则化儿化表层类：{surface_class}")
        generation = item.review.get("surface_generation") or {}
        if generation:
            method = str(generation.get("method") or "")
            lines.append(
                "表层生成方式："
                + ("规则自动生成" if method == "rule_generated" else "人工例外覆盖")
            )
        if item.source_note:
            lines.append(f"来源备注：{item.source_note}")
        if not item.source_annotations:
            lines.extend(("", "PSC 儿化韵表中没有与本项对齐的类别。"))
            return "\n".join(lines)
        for number, annotation in enumerate(item.source_annotations, start=1):
            analysis = annotation.get("ipa_analysis") or {}
            alignment = annotation.get("alignment") or {}
            examples = "、".join(
                f"{example.get('hanzi', '')} {example.get('pinyin_nfc', '')}".strip()
                for example in annotation.get("examples") or []
            )
            lines.extend(
                (
                    "",
                    f"【来源 {number}】PSC 第 {annotation.get('source_index')} 类，第 {annotation.get('source_page')} 页",
                    f"原规则：{annotation.get('source_rule')}    鼻化：{'是' if annotation.get('nasalized') else '否'}",
                    f"工程对齐：{alignment.get('status')} → {alignment.get('project_final')}",
                    f"IPA 工作候选：{' / '.join(analysis.get('unpitched_candidates') or [])}",
                    f"现有变化假设：{analysis.get('operation') or '—'}",
                    f"卷舌范围标签：{analysis.get('rhotic_scope') or '—'}",
                    f"词例：{examples or '—'}",
                )
            )
            if alignment.get("note"):
                lines.append(f"对齐疑点：{alignment['note']}")
        return "\n".join(lines)

    def _surface_segments(self) -> dict[str, dict[str, object]]:
        return {
            name: {
                "quality": self.surface_vars[name].get().strip(),
                "features": {
                    "rhotic": self.rhotic_vars[name].get(),
                    "nasalized": self.nasalized_vars[name].get(),
                },
            }
            for name in SEGMENT_NAMES
        }

    def copy_base_segments(self) -> None:
        item = self.item_by_final.get(self.current_final)
        if not item:
            return
        for name in SEGMENT_NAMES:
            self.surface_vars[name].set(item.base_segments[name])
            self.rhotic_vars[name].set(False)
            self.nasalized_vars[name].set(False)

    def clear_surface_segments(self) -> None:
        for name in SEGMENT_NAMES:
            self.surface_vars[name].set("")
            self.rhotic_vars[name].set(False)
            self.nasalized_vars[name].set(False)

    def _adjacent_final(self, offset: int) -> str:
        keys = [item.final for item in self.visible]
        if not keys or self.current_final not in keys:
            return ""
        return keys[(keys.index(self.current_final) + offset) % len(keys)]

    def _go(self, offset: int) -> None:
        target = self._adjacent_final(offset)
        if not target or not self._confirm_discard():
            return
        self.tree.selection_set(target)
        self.tree.focus(target)
        self.tree.see(target)
        self.show(self.item_by_final[target])

    def previous(self) -> None:
        self._go(-1)

    def next(self) -> None:
        self._go(1)

    def save_decision(self, decision: str, *, advance: bool) -> None:
        if not self.current_final:
            return
        next_final = self._adjacent_final(1) if advance else self.current_final
        try:
            self.store.save_review(
                self.current_final,
                surface_segments=self._surface_segments(),
                decision=decision,
                note=self.note_text.get("1.0", "end").strip(),
            )
        except Exception as error:
            messagebox.showerror("保存失败", str(error), parent=self.root)
            return
        self._dirty = False
        self.reload(next_final)

    def clear_review(self) -> None:
        if not self.current_final:
            return
        if not messagebox.askyesno("撤销标注", f"撤销 {self.current_final} 的三段标注吗？", parent=self.root):
            return
        current = self.current_final
        try:
            self.store.clear_review(current)
        except Exception as error:
            messagebox.showerror("撤销失败", str(error), parent=self.root)
            return
        self._dirty = False
        self.reload(current)

    def _confirm_discard(self) -> bool:
        if not self._dirty:
            return True
        answer = messagebox.askyesnocancel(
            "尚未保存",
            "当前三段标注尚未保存。\n\n选择“是”按已标注保存；选择“否”放弃本次编辑。",
            parent=self.root,
        )
        if answer is None:
            return False
        if answer:
            before = self._dirty
            self.save_decision("reviewed", advance=False)
            return before and not self._dirty
        self._dirty = False
        return True

    def close(self) -> None:
        if self._confirm_discard():
            self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", type=Path, default=DEFAULT_DRAFT)
    parser.add_argument("--decomposition", type=Path, default=DEFAULT_DECOMPOSITION)
    parser.add_argument("--smoke-test", action="store_true", help="只验证数据和模型，不打开窗口")
    parser.add_argument("--ui-smoke-test", action="store_true", help="构造完整界面后自动关闭")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    store = ErhuaFinalDraftStore(args.draft, args.decomposition)
    items = store.load_items()
    if args.smoke_test:
        counts: dict[str, int] = {}
        groups: dict[str, str] = {}
        for item in items:
            counts[item.decision] = counts.get(item.decision, 0) + 1
            for group in item.psc_result_groups:
                groups[str(group["key"])] = str(group["label"])
        print(
            json.dumps(
                {
                    "items": len(items),
                    "decisions": counts,
                    "psc_result_group_count": len(groups),
                    "psc_result_groups": list(groups.values()),
                },
                ensure_ascii=False,
            )
        )
        return 0
    application = ReviewApplication(store)
    if args.ui_smoke_test:
        application.root.after(300, application.root.destroy)
    application.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
