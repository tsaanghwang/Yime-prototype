"""In-memory draft model for the keyboard layout workbench."""

from __future__ import annotations

import copy
import json
import sqlite3
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, cast

from yime.utils.yinyuan_id_chain import (
    expected_yinyuan_ids,
    load_semantic_yinyuan_registry,
)


CANDIDATE_KEY_TOKENS = set("!@#$%^&*(")


@dataclass(frozen=True)
class DraftValidation:
    issues: tuple[str, ...]

    @property
    def accepted(self) -> bool:
        return not self.issues


@dataclass(frozen=True)
class TrialResult:
    yinyuan_ids: tuple[str, ...]
    unknown_tokens: tuple[str, ...]
    candidates: tuple[tuple[str, str], ...]
    query_codepoints: str = ""


@dataclass(frozen=True)
class LexiconStatus:
    connected: bool
    db_path: Path
    row_count: int = 0
    code_column: str = ""
    error: str = ""

    @property
    def display(self) -> str:
        if not self.connected:
            return f"✗ 词库未连接：{self.error or self.db_path}"
        return (
            f"✓ 词库已连接：{self.db_path.name}｜{self.row_count:,} 条｜"
            f"查询字段 {self.code_column}｜键面 → Yinyuan ID → canonical 码 → 候选"
        )


@dataclass(frozen=True)
class LexiconProbe:
    linked: bool
    typed_keys: str = ""
    candidate_count: int = 0
    error: str = ""

    @property
    def display(self) -> str:
        if not self.linked:
            return f"✗ 键面—词库端到端验证失败：{self.error}"
        return (
            f"✓ 端到端验证：当前键面 ba1 → {self.typed_keys} → "
            f"取得 {self.candidate_count} 个候选"
        )


def _native_literal(entry: dict[str, Any]) -> str | None:
    physical_key = str(entry.get("physical_key") or "")
    display_label = str(entry.get("display_label") or "")
    if physical_key == "space":
        return " "
    return display_label if len(display_label) == 1 else None


class LayoutDraft:
    """A layout candidate that does not touch the canonical JSON until accepted."""

    def __init__(self, payload: dict[str, Any], repo_root: Path) -> None:
        self.repo_root = repo_root
        self.payload = copy.deepcopy(payload)
        self.registry = load_semantic_yinyuan_registry(repo_root)
        self.canonical_symbols = cast(
            dict[str, str],
            json.loads(
                (repo_root / "internal_data" / "key_to_symbol.json").read_text(
                    encoding="utf-8"
                )
            ),
        )

    @classmethod
    def load(cls, repo_root: Path) -> "LayoutDraft":
        path = repo_root / "internal_data" / "manual_key_layout.json"
        return cls(cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8"))), repo_root)

    @property
    def layers(self) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], self.payload["layers"])

    def slot(self, order: int) -> dict[str, Any]:
        for entry in self.layers:
            if int(entry.get("order") or 0) == order:
                return entry
        raise KeyError(f"Unknown layout slot order: {order}")

    @staticmethod
    def is_locked(entry: dict[str, Any]) -> bool:
        display_label = str(entry.get("display_label") or "")
        return (
            str(entry.get("output_layer") or "") == "altgr"
            or str(entry.get("physical_key") or "") == "`"
            or display_label in CANDIDATE_KEY_TOKENS
        )

    def assign(self, order: int, yinyuan_id: str | None) -> None:
        target = self.slot(order)
        if self.is_locked(target):
            raise ValueError("该键位受布局锁保护，不能分配音元")
        if yinyuan_id is not None and yinyuan_id not in expected_yinyuan_ids():
            raise ValueError(f"未知 Yinyuan ID：{yinyuan_id}")

        previous_id = cast(str | None, target.get("yinyuan_id"))
        source = next(
            (
                entry
                for entry in self.layers
                if entry.get("yinyuan_id") == yinyuan_id and entry is not target
            ),
            None,
        )
        target["yinyuan_id"] = yinyuan_id
        target["literal_char"] = None if yinyuan_id else _native_literal(target)

        if source is not None:
            source["yinyuan_id"] = previous_id
            source["literal_char"] = None if previous_id else _native_literal(source)

    def validate(self) -> DraftValidation:
        issues: list[str] = []
        seen_slots: set[tuple[str, str]] = set()
        id_to_slot: dict[str, str] = {}

        for entry in self.layers:
            physical_key = str(entry.get("physical_key") or "")
            output_layer = str(entry.get("output_layer") or "")
            display_label = str(entry.get("display_label") or "")
            slot_key = (physical_key, output_layer)
            if slot_key in seen_slots:
                issues.append(f"键位重复：{physical_key}/{output_layer}")
            seen_slots.add(slot_key)

            yinyuan_id = str(entry.get("yinyuan_id") or "")
            if not yinyuan_id:
                continue
            if yinyuan_id not in expected_yinyuan_ids():
                issues.append(f"未知 Yinyuan ID：{yinyuan_id}")
                continue
            if output_layer not in {"base", "shift"}:
                issues.append(f"{yinyuan_id} 被放入禁用层 {output_layer}")
            if physical_key == "`" or display_label in CANDIDATE_KEY_TOKENS:
                issues.append(f"{yinyuan_id} 占用了保留键 {display_label}")
            if yinyuan_id in id_to_slot:
                issues.append(f"{yinyuan_id} 重复：{id_to_slot[yinyuan_id]}、{display_label}")
            else:
                id_to_slot[yinyuan_id] = display_label

        expected = expected_yinyuan_ids()
        assigned = set(id_to_slot)
        missing = sorted(expected - assigned)
        if missing:
            issues.append("尚未分配：" + " ".join(missing))
        return DraftValidation(tuple(issues))

    def token_to_id(self) -> dict[str, str]:
        return {
            str(entry["display_label"]): str(entry["yinyuan_id"])
            for entry in self.layers
            if entry.get("yinyuan_id") and len(str(entry.get("display_label") or "")) == 1
        }

    def trial_ids(self, typed_text: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
        token_to_id = self.token_to_id()
        ids: list[str] = []
        unknown: list[str] = []
        for token in typed_text:
            yinyuan_id = token_to_id.get(token)
            if yinyuan_id:
                ids.append(yinyuan_id)
            elif not token.isspace():
                unknown.append(token)
        return tuple(ids), tuple(unknown)

    def trial(self, typed_text: str, *, limit: int = 20) -> TrialResult:
        ids, unknown = self.trial_ids(typed_text)
        if not ids or unknown:
            return TrialResult(ids, unknown, ())
        code = "".join(self.canonical_symbols[yinyuan_id] for yinyuan_id in ids)
        candidates = lookup_candidates(
            self.repo_root / "yime" / "pinyin_hanzi.db",
            code,
            limit=limit,
        )
        codepoints = " ".join(f"U+{ord(symbol):06X}" for symbol in code)
        return TrialResult(ids, unknown, candidates, codepoints)

    def describe_id(self, yinyuan_id: str) -> str:
        entry = self.registry[yinyuan_id]
        return f"{yinyuan_id}  {entry['label']}"

    def serialized(self) -> str:
        return json.dumps(self.payload, ensure_ascii=False, indent=2) + "\n"


def lookup_candidates(
    db_path: Path,
    canonical_code: str,
    *,
    limit: int = 20,
) -> tuple[tuple[str, str], ...]:
    status = inspect_lexicon(db_path)
    if not status.connected or not canonical_code:
        return ()
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        code_column = status.code_column
        rows = conn.execute(
            f"""
            SELECT text, pinyin_tone
            FROM runtime_candidates_materialized
            WHERE {code_column} >= ? AND {code_column} < ?
            ORDER BY
                CASE WHEN {code_column} = ? THEN 0 ELSE 1 END,
                CASE
                    WHEN entry_type = 'phrase' AND text_length BETWEEN 2 AND 4 THEN 0
                    WHEN entry_type = 'char' THEN 1
                    ELSE 2
                END,
                sort_weight DESC,
                text
            LIMIT ?
            """,
            (canonical_code, canonical_code + chr(0x10FFFF), canonical_code, limit),
        ).fetchall()
    except sqlite3.Error:
        return ()
    finally:
        conn.close()
    return tuple((str(text), str(pinyin)) for text, pinyin in rows)


@lru_cache(maxsize=4)
def inspect_lexicon(db_path: Path) -> LexiconStatus:
    if not db_path.exists():
        return LexiconStatus(False, db_path, error="数据库文件不存在")
    try:
        conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        try:
            table = conn.execute(
                """
                SELECT 1 FROM sqlite_master
                WHERE type = 'table' AND name = 'runtime_candidates_materialized'
                """
            ).fetchone()
            if table is None:
                return LexiconStatus(False, db_path, error="缺少 runtime_candidates_materialized")
            columns = {
                str(row[1])
                for row in conn.execute("PRAGMA table_info(runtime_candidates_materialized)")
            }
            code_column = next(
                (
                    candidate
                    for candidate in (
                        "variable_yinyuan_code",
                        "primary_yime_code",
                        "yime_code",
                    )
                    if candidate in columns
                ),
                "",
            )
            if not code_column:
                return LexiconStatus(False, db_path, error="候选表没有可查询的 Yime 码字段")
            row_count = int(
                conn.execute("SELECT COUNT(*) FROM runtime_candidates_materialized").fetchone()[0]
            )
            return LexiconStatus(True, db_path, row_count, code_column)
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return LexiconStatus(False, db_path, error=str(exc))


def probe_lexicon_link(draft: LayoutDraft) -> LexiconProbe:
    """Prove that current keycaps reach the canonical ba1 lexicon bucket."""
    id_to_token = {
        yinyuan_id: token for token, yinyuan_id in draft.token_to_id().items()
    }
    probe_ids = ("N01", "M10", "M10", "M10")
    missing = [yinyuan_id for yinyuan_id in probe_ids if yinyuan_id not in id_to_token]
    if missing:
        return LexiconProbe(False, error="当前草案缺少 " + " ".join(missing))
    typed_keys = "".join(id_to_token[yinyuan_id] for yinyuan_id in probe_ids)
    result = draft.trial(typed_keys)
    matching = tuple(
        candidate for candidate in result.candidates if candidate[1] == "ba1"
    )
    if not matching:
        return LexiconProbe(False, typed_keys, error="ba1 没有返回候选")
    return LexiconProbe(True, typed_keys, len(matching))


def write_canonical_layout_atomic(repo_root: Path, serialized: str) -> None:
    layout_path = repo_root / "internal_data" / "manual_key_layout.json"
    temporary_path = layout_path.with_suffix(".json.tmp")
    temporary_path.write_text(serialized, encoding="utf-8")
    temporary_path.replace(layout_path)


def format_trial_result(draft: LayoutDraft, result: TrialResult) -> str:
    parts: list[str] = []
    if result.yinyuan_ids:
        parts.append("音元：" + "  ".join(draft.describe_id(item) for item in result.yinyuan_ids))
    if result.unknown_tokens:
        parts.append("非音元键：" + " ".join(repr(item) for item in result.unknown_tokens))
    if result.query_codepoints:
        parts.append("词库查询码：" + result.query_codepoints)
    if result.candidates:
        parts.append(
            "候选：" + "  ".join(
                f"{index}. {text}〔{pinyin}〕"
                for index, (text, pinyin) in enumerate(result.candidates, start=1)
            )
        )
    elif result.yinyuan_ids and not result.unknown_tokens:
        parts.append("候选：当前码串没有精确候选")
    return "\n".join(parts)


def assigned_ids(entries: Iterable[dict[str, Any]]) -> set[str]:
    return {str(entry["yinyuan_id"]) for entry in entries if entry.get("yinyuan_id")}
