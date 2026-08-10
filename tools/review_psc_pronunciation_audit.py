#!/usr/bin/env python3
"""First-stage UI for checking PSC source transcriptions.

The UI may show prototype readings as a diagnostic reference, but its decisions
only describe whether the transcribed Hanzi--Pinyin pair agrees with the source
material.  It never writes the PSC database or the prototype lexicon database.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import webbrowser
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from yime.lexicon_bundle.psc_transcription_review import (
    TranscriptionReviewItem,
    TranscriptionReviewStore,
    next_visible_key_after_save,
)


SOURCE_LABELS = {
    "psc_main": "单/多音节注音表",
    "psc_neutral_tone": "轻声词表",
    "psc_erhua": "儿化词表",
    "psc_rare_word": "生僻字难点字词",
    "psc_passage": "短文语音提示",
}

DECISION_LABELS = {
    "pending": "待校核",
    "machine_verified": "机器初校：暂不需人工校核",
    "confirmed": "转录正确",
    "corrected": "转录有误，已登记校正",
    "unresolved": "暂时无法确认",
    "stale": "来源记录已变化，需重校",
}

STATE_LABELS = (
    "待校核",
    "全部状态",
    "机器初校：暂不需人工校核",
    "转录正确",
    "转录有误，已登记校正",
    "暂时无法确认",
    "来源记录已变化，需重校",
)

SCOPE_LABELS = ("参照差异（推荐）", "全部来源记录")


def _read_only_connection(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


class SourceMaterialResolver:
    """Resolve source locations and render the already-generated main-table crops."""

    def __init__(self, database: Path) -> None:
        self.database = database.resolve()
        self.connection = _read_only_connection(self.database)
        self.root = self.database.parent
        self.documents = {
            int(row["id"]): Path(str(row["source_path"]))
            for row in self.connection.execute("SELECT id, source_path FROM documents")
        }

    def close(self) -> None:
        self.connection.close()

    def source_path(self, item: TranscriptionReviewItem) -> Path | None:
        query: str
        params: tuple[object, ...]
        if item.source_kind == "psc_main":
            table_number, source_index = (int(part) for part in item.source_key.split(":"))
            query = "SELECT document_id FROM entries WHERE table_number=? AND source_index=?"
            params = (table_number, source_index)
        elif item.source_kind == "psc_neutral_tone":
            query = """
                SELECT d.document_id FROM neutral_tone_entries AS e
                JOIN neutral_tone_datasets AS d ON d.id=e.dataset_id
                WHERE e.source_index=?
            """
            params = (item.source_order,)
        elif item.source_kind == "psc_erhua":
            query = """
                SELECT d.document_id FROM erhua_entries AS e
                JOIN erhua_datasets AS d ON d.id=e.dataset_id
                WHERE e.source_index=?
            """
            params = (item.source_order,)
        elif item.source_kind == "psc_rare_word":
            query = """
                SELECT d.reference_document_id AS document_id
                FROM rare_word_entries AS e
                JOIN rare_word_datasets AS d ON d.id=e.dataset_id
                WHERE e.source_index=?
            """
            params = (item.source_order,)
        elif item.source_kind == "psc_passage":
            query = """
                SELECT d.pdf_document_id AS document_id
                FROM passage_pronunciation_entries AS e
                JOIN passage_pronunciation_datasets AS d ON d.id=e.dataset_id
                WHERE e.source_index=?
            """
            params = (item.source_order,)
        else:
            return None
        row = self.connection.execute(query, params).fetchone()
        return self.documents.get(int(row["document_id"])) if row else None

    @staticmethod
    def page_number(item: TranscriptionReviewItem) -> int | None:
        value = item.locator.get("page_number")
        if value is None:
            value = item.locator.get("pdf_page_number")
        return int(value) if value is not None else None

    def location_text(self, item: TranscriptionReviewItem) -> str:
        source = SOURCE_LABELS.get(item.source_kind, item.source_kind)
        locator = item.locator
        details: list[str] = [source, f"记录 {item.source_key}"]
        page = self.page_number(item)
        if page is not None:
            details.append(f"第 {page} 页")
        if locator.get("column_number") is not None:
            details.append(f"第 {locator['column_number']} 栏")
        if locator.get("source_row") is not None:
            details.append(f"源行 {locator['source_row']}")
        if locator.get("work_no") is not None:
            details.append(f"作品 {locator['work_no']}《{locator.get('title', '')}》")
        return "　".join(details)

    def open_source(self, item: TranscriptionReviewItem) -> None:
        path = self.source_path(item)
        if path is None or not path.is_file():
            raise FileNotFoundError(path or "未找到来源材料")
        page = self.page_number(item)
        if page and path.suffix.lower() == ".pdf":
            webbrowser.open(f"{path.as_uri()}#page={page}")
        else:
            os.startfile(path)  # type: ignore[attr-defined]

    def main_table_preview(self, item: TranscriptionReviewItem) -> Any | None:
        if item.source_kind != "psc_main":
            return None
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            return None
        table_number, source_index = (int(part) for part in item.source_key.split(":"))
        entry = self.connection.execute(
            """
            SELECT document_id, page_number, column_number, evidence_span_ids_json
              FROM entries WHERE table_number=? AND source_index=?
            """,
            (table_number, source_index),
        ).fetchone()
        if entry is None:
            return None
        page_number = int(entry["page_number"])
        image_path = self.root / "pages" / f"page-{page_number:04d}.png"
        if not image_path.is_file():
            return None
        span_ids = tuple(int(value) for value in json.loads(entry["evidence_span_ids_json"]))
        boxes: Sequence[sqlite3.Row] = ()
        if span_ids:
            placeholders = ",".join("?" for _ in span_ids)
            boxes = self.connection.execute(
                f"""
                SELECT x1, y1, x2, y2 FROM ocr_spans
                 WHERE id IN ({placeholders}) ORDER BY span_order
                """,
                span_ids,
            ).fetchall()
        image = Image.open(image_path).convert("RGBA")
        width, height = image.size
        center_y = (
            (min(float(row["y1"]) for row in boxes) + max(float(row["y2"]) for row in boxes))
            / 2.0
            if boxes
            else height / 2.0
        )
        column = int(entry["column_number"])
        column_width = width / 3.0
        left = max(0, int((column - 1) * column_width - 30))
        right = min(width, int(column * column_width + 30))
        top = max(0, int(center_y - 105))
        bottom = min(height, int(center_y + 105))
        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        for row in boxes:
            draw.rectangle(
                (float(row["x1"]), float(row["y1"]), float(row["x2"]), float(row["y2"])),
                outline=(220, 35, 35, 255),
                width=3,
            )
        crop = Image.alpha_composite(image, overlay).crop((left, top, right, bottom)).convert("RGB")
        maximum = (930, 245)
        scale = min(maximum[0] / crop.width, maximum[1] / crop.height, 2.5)
        target = (max(1, round(crop.width * scale)), max(1, round(crop.height * scale)))
        return crop.resize(target, Image.Resampling.LANCZOS)


class ReviewApplication:
    def __init__(
        self,
        store: TranscriptionReviewStore,
        source: SourceMaterialResolver,
        *,
        smoke_test: bool = False,
    ) -> None:
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.ttk = ttk
        self.store = store
        self.source = source
        self.all_items: list[TranscriptionReviewItem] = []
        self.items: list[TranscriptionReviewItem] = []
        self.item_by_key: dict[str, TranscriptionReviewItem] = {}
        self.current_photo = None
        self._closed = False

        self.root = tk.Tk()
        self.root.title("PSC 来源材料转录校核")
        self.root.geometry("1500x920")
        self.root.minsize(1120, 720)
        self.root.option_add("*Font", ("Microsoft YaHei UI", 10))
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 17, "bold"))
        style.configure("Word.TLabel", font=("Microsoft YaHei UI", 22, "bold"))
        style.configure("Pinyin.TLabel", font=("Microsoft YaHei UI", 16))

        self.scope_var = tk.StringVar(value=SCOPE_LABELS[0])
        self.source_var = tk.StringVar(value="全部来源")
        self.state_var = tk.StringVar(value=STATE_LABELS[0])
        self.search_var = tk.StringVar()
        self.progress_var = tk.StringVar()
        self.location_var = tk.StringVar()
        self.status_var = tk.StringVar()
        self.text_var = tk.StringVar()
        self.pinyin_var = tk.StringVar()
        self._build_ui()
        self._bind_keys()
        self.refresh_data()
        if smoke_test:
            self.root.after(200, self.close)

    def _combo(self, parent: object, label: str, variable: object, values: Sequence[str], width: int) -> None:
        self.ttk.Label(parent, text=label).pack(side="left", padx=(10, 4))
        box = self.ttk.Combobox(parent, textvariable=variable, values=values, state="readonly", width=width)
        box.pack(side="left")
        box.bind("<<ComboboxSelected>>", lambda _event: self.apply_filter())

    def _build_ui(self) -> None:
        tk, ttk = self.tk, self.ttk
        top = ttk.Frame(self.root, padding=(14, 10, 14, 6))
        top.pack(fill="x")
        ttk.Label(top, text="PSC 来源材料转录校核", style="Title.TLabel").pack(side="left")
        ttk.Label(top, textvariable=self.progress_var).pack(side="right")
        ttk.Label(
            self.root,
            text="第一阶段只核对词形—拼音转录是否忠实；不处理轻声主次、读音排序，也不修改原型注音。",
            padding=(14, 0, 14, 8),
        ).pack(fill="x")

        controls = ttk.Frame(self.root, padding=(4, 0, 14, 8))
        controls.pack(fill="x")
        self._combo(controls, "范围：", self.scope_var, SCOPE_LABELS, 18)
        self._combo(controls, "来源：", self.source_var, ("全部来源", *SOURCE_LABELS.values()), 18)
        self._combo(controls, "状态：", self.state_var, STATE_LABELS, 30)
        ttk.Label(controls, text="查找：").pack(side="left", padx=(10, 4))
        search = ttk.Entry(controls, textvariable=self.search_var, width=22)
        search.pack(side="left")
        search.bind("<Return>", lambda _event: self.apply_filter())
        ttk.Button(controls, text="筛选", command=self.apply_filter).pack(side="left", padx=4)
        ttk.Button(controls, text="刷新", command=self.refresh_data).pack(side="left")

        panes = ttk.Panedwindow(self.root, orient="horizontal")
        panes.pack(fill="both", expand=True, padx=14, pady=(0, 8))
        queue = ttk.LabelFrame(panes, text="校核队列", padding=6)
        detail = ttk.Frame(panes)
        panes.add(queue, weight=2)
        panes.add(detail, weight=5)
        self._build_queue(queue)
        self._build_detail(detail)

        nav = ttk.Frame(self.root, padding=(14, 0, 14, 12))
        nav.pack(fill="x")
        ttk.Button(nav, text="◀ 上一条", command=self.previous).pack(side="left")
        ttk.Button(nav, text="下一条 ▶", command=self.next).pack(side="left", padx=6)
        ttk.Button(nav, text="撤销本条校核", command=self.clear_current).pack(side="left", padx=(14, 0))
        ttk.Button(nav, text="暂时无法确认并下一条", command=self.unresolved_and_next).pack(side="right")
        ttk.Button(nav, text="保存校正并下一条", command=self.corrected_and_next).pack(side="right", padx=6)
        ttk.Button(nav, text="确认转录正确并下一条", command=self.confirmed_and_next).pack(side="right")

    def _build_queue(self, parent: object) -> None:
        ttk = self.ttk
        columns = ("pinyin", "source", "state")
        self.tree = ttk.Treeview(parent, columns=columns, show="tree headings")
        self.tree.heading("#0", text="词形")
        self.tree.heading("pinyin", text="转录拼音")
        self.tree.heading("source", text="来源")
        self.tree.heading("state", text="状态")
        self.tree.column("#0", width=120)
        self.tree.column("pinyin", width=170)
        self.tree.column("source", width=130)
        self.tree.column("state", width=210)
        yscroll = ttk.Scrollbar(parent, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(parent, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self.show_current())

    def _build_detail(self, parent: object) -> None:
        tk, ttk = self.tk, self.ttk
        header = ttk.Frame(parent, padding=(8, 2, 0, 6))
        header.pack(fill="x")
        ttk.Label(header, textvariable=self.location_var).pack(side="left")
        ttk.Button(header, text="打开来源材料", command=self.open_source).pack(side="right")
        ttk.Label(parent, textvariable=self.status_var, padding=(8, 0, 0, 6)).pack(fill="x")

        preview = ttk.LabelFrame(parent, text="来源位置预览", padding=6)
        preview.pack(fill="both", expand=True, padx=(8, 0), pady=(0, 8))
        self.image_label = ttk.Label(preview, anchor="center", justify="center")
        self.image_label.pack(fill="both", expand=True)

        form = ttk.LabelFrame(
            parent,
            text="有效转录内容（校正写入独立账本，不直接改写来源库）",
            padding=8,
        )
        form.pack(fill="x", padx=(8, 0), pady=(0, 8))
        ttk.Label(form, text="词形：").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(form, textvariable=self.text_var, font=("Microsoft YaHei UI", 14)).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Label(form, text="拼音：").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(form, textvariable=self.pinyin_var, font=("Microsoft YaHei UI", 13)).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Label(form, text="校核备注：").grid(row=2, column=0, sticky="nw", pady=4)
        self.note_text = tk.Text(form, height=3, wrap="word", font=("Microsoft YaHei UI", 10))
        self.note_text.grid(row=2, column=1, sticky="ew", pady=4)
        form.columnconfigure(1, weight=1)

        reference = ttk.LabelFrame(parent, text="原型参考（仅用于发现转录异常；本阶段不裁决）", padding=8)
        reference.pack(fill="both", expand=True, padx=(8, 0))
        self.reference_text = tk.Text(reference, height=10, wrap="word", background="#f5f5f5", font=("Microsoft YaHei UI", 10))
        scroll = ttk.Scrollbar(reference, orient="vertical", command=self.reference_text.yview)
        self.reference_text.configure(yscrollcommand=scroll.set)
        self.reference_text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    def _bind_keys(self) -> None:
        self.root.bind("<F7>", lambda _event: self.previous())
        self.root.bind("<F8>", lambda _event: self.next())
        self.root.bind("<Control-Return>", lambda _event: self.confirmed_and_next())
        self.root.bind("<Control-s>", lambda _event: self.corrected_and_next())

    def refresh_data(self, select_key: str | None = None) -> None:
        previous = select_key or self.current_key()
        self.all_items = self.store.load_items()
        self.item_by_key = {item.record_key: item for item in self.all_items}
        self.apply_filter(previous)

    def _state_matches(self, item: TranscriptionReviewItem) -> bool:
        selected = self.state_var.get()
        if selected == "全部状态":
            return True
        if selected == "来源记录已变化，需重校":
            return item.stale_decision
        wanted = next((key for key, label in DECISION_LABELS.items() if label == selected), None)
        return item.review_state == wanted

    def apply_filter(self, select_key: str | None = None) -> None:
        needle = self.search_var.get().strip().lower()
        selected_source = self.source_var.get()
        attention_only = self.scope_var.get() == "参照差异（推荐）"
        self.items = [
            item for item in self.all_items
            if (not attention_only or item.needs_reference_check)
            and (selected_source == "全部来源" or SOURCE_LABELS.get(item.source_kind) == selected_source)
            and self._state_matches(item)
            and (not needle or needle in f"{item.text} {item.pinyin} {item.source_key}".lower())
        ]
        current = select_key or self.current_key()
        self.tree.delete(*self.tree.get_children())
        for item in self.items:
            self.tree.insert(
                "",
                "end",
                iid=item.record_key,
                text=item.effective_text or "（空词形）",
                values=(
                    item.effective_pinyin or "（空拼音）",
                    SOURCE_LABELS.get(item.source_kind, item.source_kind),
                    DECISION_LABELS[item.review_state],
                ),
            )
        keys = {item.record_key for item in self.items}
        target = current if current in keys else (self.items[0].record_key if self.items else None)
        if target:
            self.tree.selection_set(target)
            self.tree.focus(target)
            self.tree.see(target)
        stats = self.store.stats(self.all_items)
        self.progress_var.set(
            f"机器初校 {stats['machine_verified']} / 待校核 {stats['pending']} / "
            f"人工确认 {stats['confirmed']} / 已校正 {stats['corrected']} / "
            f"待查 {stats['unresolved']}"
        )
        self.show_current()

    def current_key(self) -> str | None:
        selected = self.tree.selection() if hasattr(self, "tree") else ()
        return str(selected[0]) if selected else None

    def current(self) -> TranscriptionReviewItem | None:
        key = self.current_key()
        return self.item_by_key.get(key) if key else None

    def _reference_lines(self, item: TranscriptionReviewItem) -> list[str]:
        def readings(title: str, values: Sequence[dict[str, object]]) -> list[str]:
            lines = [title]
            if not values:
                return [title, "  （无记录）"]
            for value in values:
                lines.append(f"  - {value.get('marked', '')}  [{value.get('numeric', '')}]　来源={value.get('sources', '')}")
            return lines
        return [
            "注意：下列内容仅帮助发现错字、漏字、错位、调号或分隔符转录异常。",
            "本阶段不据此决定哪一读音正确、是否轻声、是否主读，也不修改原型。",
            "",
            f"原转录：{item.text}　{item.pinyin}",
            f"当前有效转录：{item.effective_text}　{item.effective_pinyin}",
            "",
            *readings("原型 canonical_readings：", item.canonical_readings),
            "",
            *readings("原型 accepted_readings：", item.accepted_readings),
            "",
            f"旧差异分类（仅用于排队）：{item.review_lane}",
            f"旧比较说明（不作为本阶段裁决）：{item.explanation}",
            "",
            "来源定位：",
            json.dumps(item.locator, ensure_ascii=False, indent=2),
        ]

    def show_current(self) -> None:
        item = self.current()
        self.current_photo = None
        if item is None:
            self.location_var.set("当前筛选条件下没有记录")
            self.status_var.set("")
            self.text_var.set("")
            self.pinyin_var.set("")
            self.note_text.delete("1.0", "end")
            self.reference_text.configure(state="normal")
            self.reference_text.delete("1.0", "end")
            self.reference_text.configure(state="disabled")
            self.image_label.configure(image="", text="没有待显示的记录")
            return
        index = next((i for i, value in enumerate(self.items) if value.record_key == item.record_key), 0)
        self.location_var.set(f"{index + 1}/{len(self.items)}　{self.source.location_text(item)}")
        status = f"状态：{DECISION_LABELS[item.review_state]}　当前阶段只核对来源转录。"
        if item.review_state == "machine_verified":
            status += "　第一轮经机器（程序）校核，初步判定无转录错误，暂时不需人工校核。"
        if item.decision == "corrected" and not item.stale_decision:
            status += (
                f"　原转录：{item.text} / {item.pinyin}"
                f"　→　有效转录：{item.effective_text} / {item.effective_pinyin}"
            )
        self.status_var.set(status)
        self.text_var.set(item.corrected_text or item.text)
        self.pinyin_var.set(item.corrected_pinyin or item.pinyin)
        self.note_text.delete("1.0", "end")
        self.note_text.insert("1.0", item.note)
        self.reference_text.configure(state="normal")
        self.reference_text.delete("1.0", "end")
        self.reference_text.insert("1.0", "\n".join(self._reference_lines(item)))
        self.reference_text.configure(state="disabled")
        try:
            crop = self.source.main_table_preview(item)
            if crop is None:
                path = self.source.source_path(item)
                page = self.source.page_number(item)
                suffix = f"，定位第 {page} 页" if page else ""
                self.image_label.configure(image="", text=f"当前来源没有内嵌页图预览{suffix}。\n可点击“打开来源材料”核对。\n{path or ''}")
            else:
                from PIL import ImageTk
                self.current_photo = ImageTk.PhotoImage(crop)
                self.image_label.configure(image=self.current_photo, text="")
        except Exception as error:
            self.image_label.configure(image="", text=f"来源预览加载失败：{error}")

    def _values(self) -> tuple[str, str, str]:
        return self.text_var.get().strip(), self.pinyin_var.get().strip(), self.note_text.get("1.0", "end").strip()

    def _save(self, decision: str) -> bool:
        from tkinter import messagebox
        item = self.current()
        if item is None:
            return False
        text, pinyin, note = self._values()
        try:
            self.store.save(item, decision, text, pinyin, note)
        except (ValueError, sqlite3.Error) as error:
            messagebox.showwarning("无法保存", str(error))
            return False
        return True

    def _after_save(self) -> None:
        previous_keys = list(self.tree.get_children())
        current_key = self.current_key()
        self.all_items = self.store.load_items()
        self.item_by_key = {item.record_key: item for item in self.all_items}
        self.apply_filter()
        refreshed_keys = list(self.tree.get_children())
        target = next_visible_key_after_save(previous_keys, current_key, refreshed_keys)
        if target:
            self.tree.selection_set(target)
            self.tree.focus(target)
            self.tree.see(target)
            self.show_current()

    def confirmed_and_next(self) -> None:
        item = self.current()
        if item is not None:
            self.text_var.set(item.text)
            self.pinyin_var.set(item.pinyin)
        if self._save("confirmed"):
            self._after_save()

    def corrected_and_next(self) -> None:
        if self._save("corrected"):
            self._after_save()

    def unresolved_and_next(self) -> None:
        if self._save("unresolved"):
            self._after_save()

    def clear_current(self) -> None:
        from tkinter import messagebox
        item = self.current()
        if item is None or (item.decision == "pending" and not item.stale_decision):
            return
        if messagebox.askyesno("撤销校核", "撤销本条来源转录校核决定？"):
            self.store.clear(item)
            self.refresh_data(item.record_key)

    def previous(self) -> None:
        children = self.tree.get_children()
        if not children:
            return
        current = self.current_key()
        index = children.index(current) if current in children else 0
        target = children[(index - 1) % len(children)]
        self.tree.selection_set(target); self.tree.focus(target); self.tree.see(target); self.show_current()

    def next(self) -> None:
        children = self.tree.get_children()
        if not children:
            return
        current = self.current_key()
        index = children.index(current) if current in children else -1
        target = children[(index + 1) % len(children)]
        self.tree.selection_set(target); self.tree.focus(target); self.tree.see(target); self.show_current()

    def open_source(self) -> None:
        from tkinter import messagebox
        item = self.current()
        if item is None:
            return
        try:
            self.source.open_source(item)
        except (OSError, FileNotFoundError) as error:
            messagebox.showwarning("无法打开来源材料", str(error))

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.source.close()
        self.store.close()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=ROOT / ".generated" / "psc_pronunciation_audit" / "psc_pronunciation_audit.sqlite3")
    parser.add_argument("--decision-database", type=Path)
    parser.add_argument("--smoke-test", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    store = TranscriptionReviewStore(args.database, args.decision_database)
    source_path = Path(str(store.audit_inputs()["source_material"]["path"]))
    source = SourceMaterialResolver(source_path)
    app = ReviewApplication(store, source, smoke_test=args.smoke_test)
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
