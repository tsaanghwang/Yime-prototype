"""Export the canonical Pinyin-to-Yinyuan decomposition as an inspectable table.

The table is a read-only view of the real encoder stages.  It must never grow a
second Pinyin parser or infer Yinyuan IDs from keyboard keys.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from syllable.codec.yinjie_encoder import YinjieEncoder
from yime.utils.yinyuan_id_chain import (
    REPO_ROOT,
    load_semantic_yinyuan_registry,
    load_symbol_to_yinyuan_id,
    load_yinyuan_id_to_layout_key,
)


DEFAULT_INVENTORY_PATH = (
    REPO_ROOT / "internal_data" / "pinyin_source_db" / "lexicon_exports" / "pinyin_normalized.json"
)
DEFAULT_OUTPUT_PATH = REPO_ROOT / "internal_data" / "yime_syllable_decomposition.tsv"


@dataclass(frozen=True)
class SyllableDecompositionRow:
    pinyin_tone: str
    marked_pinyin: str
    normalized: str
    shouyin_label: str
    ganyin_label: str
    rule_id: str
    shouyin_symbol: str
    huyin_symbol: str
    zhuyin_symbol: str
    moyin_symbol: str
    shouyin_id: str
    huyin_id: str
    zhuyin_id: str
    moyin_id: str
    shouyin_name: str
    huyin_name: str
    zhuyin_name: str
    moyin_name: str
    layout_code: str
    aliases: str
    status: str


def _rule_id(pinyin_tone: str, ids: tuple[str, str, str, str]) -> str:
    initial, first_musical, _, _ = ids
    base = pinyin_tone[:-1].lower() if pinyin_tone[-1:].isdigit() else pinyin_tone.lower()
    if initial == "N12":
        if base in {"ê", "m", "n", "ng"}:
            return f"syllabic-{base}"
        return "zero-initial"
    if initial == "N23":
        if first_musical in {"M01", "M02", "M03"}:
            return "virtual-j"
        if first_musical in {"M07", "M08", "M09"}:
            return "virtual-h-rounded"
        return "virtual-y-other"
    if initial == "N24":
        return "virtual-w"
    return "regular-initial"


def build_syllable_decomposition_rows(
    inventory: dict[str, str],
    *,
    repo_root: Path = REPO_ROOT,
    encoder: YinjieEncoder | None = None,
) -> list[SyllableDecompositionRow]:
    """Run every inventory item through the canonical structured encoder."""
    resolved_encoder = encoder or YinjieEncoder()
    symbol_to_id = load_symbol_to_yinyuan_id(repo_root)
    registry = load_semantic_yinyuan_registry(repo_root)
    layout = load_yinyuan_id_to_layout_key(repo_root)

    staged: list[tuple[str, str, object, tuple[str, str, str, str]]] = []
    aliases_by_ids: dict[tuple[str, str, str, str], list[str]] = {}
    for pinyin_tone, marked_pinyin in inventory.items():
        result = resolved_encoder.encode_yinjie_structured(pinyin_tone)
        symbols = (
            result.shouyin_yinyuan,
            result.ganyin_slots.huyin,
            result.ganyin_slots.zhuyin,
            result.ganyin_slots.moyin,
        )
        try:
            ids = tuple(symbol_to_id[symbol] for symbol in symbols)
        except KeyError as error:
            raise ValueError(f"{pinyin_tone} contains an unknown Yinyuan symbol: {error}") from error
        if len(ids) != 4:
            raise ValueError(f"{pinyin_tone} did not resolve to four Yinyuan IDs: {ids}")
        typed_ids = (ids[0], ids[1], ids[2], ids[3])
        aliases_by_ids.setdefault(typed_ids, []).append(pinyin_tone)
        staged.append((pinyin_tone, str(marked_pinyin), result, typed_ids))

    rows: list[SyllableDecompositionRow] = []
    for pinyin_tone, marked_pinyin, raw_result, ids in staged:
        result = raw_result
        symbols = (
            result.shouyin_yinyuan,
            result.ganyin_slots.huyin,
            result.ganyin_slots.zhuyin,
            result.ganyin_slots.moyin,
        )
        names = tuple(registry[yinyuan_id]["label"] for yinyuan_id in ids)
        rows.append(
            SyllableDecompositionRow(
                pinyin_tone=pinyin_tone,
                marked_pinyin=marked_pinyin,
                normalized=result.segments.normalized,
                shouyin_label=result.segments.shouyin_label,
                ganyin_label=result.segments.ganyin_label,
                rule_id=_rule_id(pinyin_tone, ids),
                shouyin_symbol=symbols[0],
                huyin_symbol=symbols[1],
                zhuyin_symbol=symbols[2],
                moyin_symbol=symbols[3],
                shouyin_id=ids[0],
                huyin_id=ids[1],
                zhuyin_id=ids[2],
                moyin_id=ids[3],
                shouyin_name=names[0],
                huyin_name=names[1],
                zhuyin_name=names[2],
                moyin_name=names[3],
                layout_code="".join(layout[yinyuan_id] for yinyuan_id in ids),
                aliases=" ".join(aliases_by_ids[ids]),
                status="ok",
            )
        )
    return rows


def export_syllable_decomposition_tsv(
    output_path: Path = DEFAULT_OUTPUT_PATH,
    *,
    inventory_path: Path = DEFAULT_INVENTORY_PATH,
    repo_root: Path = REPO_ROOT,
) -> int:
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    if not isinstance(inventory, dict) or not inventory:
        raise ValueError(f"Pinyin inventory is empty or invalid: {inventory_path}")
    rows = build_syllable_decomposition_rows(inventory, repo_root=repo_root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(SyllableDecompositionRow.__dataclass_fields__)
    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(asdict(row) for row in rows)
    return len(rows)


def rule_ids(rows: Iterable[SyllableDecompositionRow]) -> set[str]:
    return {row.rule_id for row in rows}
