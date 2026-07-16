from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, cast

from syllable.codec.input_shorthand import omit_middle_tone_if_same_quality_run
from syllable.codec.variable_length_yinyuan import merge_adjacent_equal_yinyuan, transform_full_code


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]


class YimeCodeMode(StrEnum):
    """运行时可切换的三种音元输入模式。"""

    FULL = "full"
    VARIABLE = "variable"
    SHORTHAND = "shorthand"


CODE_MODE_LABELS: dict[YimeCodeMode, str] = {
    YimeCodeMode.FULL: "等长模式",
    YimeCodeMode.VARIABLE: "变长模式",
    YimeCodeMode.SHORTHAND: "省键模式",
}


LOOKUP_CODE_COLUMNS: dict[YimeCodeMode, str] = {
    YimeCodeMode.FULL: "full_yime_code",
    YimeCodeMode.VARIABLE: "variable_yinyuan_code",
    YimeCodeMode.SHORTHAND: "input_shorthand_code",
}


LEGACY_LOOKUP_CODE_COLUMNS: dict[YimeCodeMode, str] = {
    YimeCodeMode.FULL: "yime_code",
    YimeCodeMode.VARIABLE: "primary_yime_code",
    YimeCodeMode.SHORTHAND: "input_shorthand_code",
}


@dataclass(frozen=True)
class CodeModeRecord:
    full_code: str
    variable_code: str
    shorthand_code: str

    def lookup_code(self, mode: YimeCodeMode | str | object) -> str:
        normalized_mode = normalize_code_mode(mode)
        if normalized_mode == YimeCodeMode.FULL:
            return self.full_code
        if normalized_mode == YimeCodeMode.SHORTHAND:
            return self.shorthand_code
        return self.variable_code


def normalize_code_mode(value: YimeCodeMode | str | object) -> YimeCodeMode:
    normalized = str(value or "").strip().lower()
    if normalized in {"full", "fixed", "fixed_length", "等长", "等长模式"}:
        return YimeCodeMode.FULL
    if normalized in {"shorthand", "input_shorthand", "省键", "省键模式"}:
        return YimeCodeMode.SHORTHAND
    return YimeCodeMode.VARIABLE


def code_mode_label(mode: YimeCodeMode | str | object) -> str:
    return CODE_MODE_LABELS[normalize_code_mode(mode)]


def lookup_code_column(mode: YimeCodeMode | str | object, *, legacy: bool = False) -> str:
    normalized_mode = normalize_code_mode(mode)
    if legacy:
        return LEGACY_LOOKUP_CODE_COLUMNS[normalized_mode]
    return LOOKUP_CODE_COLUMNS[normalized_mode]


def _load_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


@lru_cache(maxsize=None)
def _load_ganyin_symbol_metadata_cached(repo_root_key: str) -> dict[str, dict[str, int | str]]:
    repo_root = Path(repo_root_key)
    mapping = _load_json(repo_root / "internal_data" / "yinjie_runtime_key_symbol_mapping.json")
    key_to_symbol = _load_json(repo_root / "internal_data" / "key_to_symbol.json")

    metadata: dict[str, dict[str, int | str]] = {}
    for entry in mapping.get("entries", []):
        if not isinstance(entry, dict) or entry.get("source_type") != "ganyin":
            continue
        key = str(entry.get("key") or "")
        if not key.startswith("M"):
            continue
        try:
            ordinal = int(key[1:]) - 1
        except ValueError:
            continue
        symbol = str(key_to_symbol.get(key) or entry.get("symbol") or "")
        if not symbol:
            continue
        metadata[symbol] = {
            "quality_group": ordinal // 3,
            "tone_level": ("high", "mid", "low")[ordinal % 3],
        }
    return metadata


def load_ganyin_symbol_metadata(repo_root: Path | None = None) -> dict[str, dict[str, int | str]]:
    resolved_root = repo_root or WORKSPACE_ROOT
    return _load_ganyin_symbol_metadata_cached(str(resolved_root.resolve()))


def _split_complete_four_codes(code: str) -> tuple[list[str], str]:
    complete_length = (len(code) // 4) * 4
    return (
        [code[index:index + 4] for index in range(0, complete_length, 4)],
        code[complete_length:],
    )


def _to_variable_prefix_compat(code: str, *, virtual_initial: str | None) -> str:
    merged, _ = merge_adjacent_equal_yinyuan(list(code))
    if virtual_initial and merged and merged[0] == virtual_initial:
        merged = merged[1:]
    return "".join(merged)


def _to_shorthand_syllable_code(
    full_code: str,
    *,
    virtual_initial: str | None,
    ganyin_symbol_metadata: Mapping[str, Mapping[str, Any]],
) -> str:
    merged, _ = merge_adjacent_equal_yinyuan(list(full_code))
    shouyin = ""
    ganyin = list(merged)
    if ganyin and virtual_initial and ganyin[0] == virtual_initial:
        ganyin = ganyin[1:]
    elif ganyin:
        shouyin = ganyin[0]
        ganyin = ganyin[1:]

    compressed_ganyin, _ = omit_middle_tone_if_same_quality_run(
        ganyin,
        ganyin_symbol_metadata,
    )
    return shouyin + "".join(compressed_ganyin)


def build_code_mode_record(
    full_code: str,
    *,
    virtual_initial: str | None = None,
    ganyin_symbol_metadata: Mapping[str, Mapping[str, Any]] | None = None,
) -> CodeModeRecord:
    normalized_code = str(full_code or "").strip()
    if not normalized_code:
        return CodeModeRecord("", "", "")

    metadata = ganyin_symbol_metadata or {}
    complete_codes, trailing = _split_complete_four_codes(normalized_code)
    variable_parts: list[str] = []
    shorthand_parts: list[str] = []

    for syllable_code in complete_codes:
        variable_parts.append(
            transform_full_code(
                syllable_code,
                virtual_initial=virtual_initial,
            ).variable_code
        )
        shorthand_parts.append(
            _to_shorthand_syllable_code(
                syllable_code,
                virtual_initial=virtual_initial,
                ganyin_symbol_metadata=metadata,
            )
        )

    if trailing:
        trailing_code = _to_variable_prefix_compat(trailing, virtual_initial=virtual_initial)
        variable_parts.append(trailing_code)
        shorthand_parts.append(trailing_code)

    variable_code = "".join(variable_parts)
    shorthand_code = "".join(shorthand_parts)
    return CodeModeRecord(
        full_code=normalized_code,
        variable_code=variable_code,
        shorthand_code=shorthand_code or variable_code,
    )


def build_code_mode_map(
    full_code_map: Mapping[str, str],
    *,
    virtual_initial: str | None = None,
    ganyin_symbol_metadata: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, CodeModeRecord]:
    return {
        key: build_code_mode_record(
            code,
            virtual_initial=virtual_initial,
            ganyin_symbol_metadata=ganyin_symbol_metadata,
        )
        for key, code in full_code_map.items()
        if str(key or "").strip() and str(code or "").strip()
    }
