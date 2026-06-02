#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from pathlib import Path
from typing import Iterable

from yime.utils.marked_pinyin import marked_syllable_to_numeric

PINYIN_TEXT_COMMENT_RE = re.compile(r"#.*$")

BREVE_TO_CARON: dict[str, str] = {
    "ă": "ǎ",
    "Ă": "Ǎ",
    "ĕ": "ě",
    "Ĕ": "Ě",
    "ĭ": "ǐ",
    "Ĭ": "Ǐ",
    "ŏ": "ǒ",
    "Ŏ": "Ǒ",
    "ŭ": "ǔ",
    "Ŭ": "Ǔ",
}

SPECIAL_SINGLE_SYLLABLE_PY: dict[str, str] = {
    "U+26B22": "pú",
    "U+5159": "shí",
    "U+515B": "qiān",
    "U+515D": "fēn",
    "U+515E": "háo",
    "U+5161": "bǎi",
    "U+5163": "gōng",
    "U+55E7": "jiā",
    "U+74E7": "shí",
    "U+74E9": "qiān",
    "U+74F0": "fēn",
    "U+74F1": "máo",
    "U+74F2": "tún",
    "U+74FC": "lǐ",
    "U+7505": "lí",
}

TONE_MARK_CHARS = "āáǎàēéěèếềīíǐìōóǒòūúǔùǖǘǚǜńňǹḿ̄́̌̀"

HEADER_NOTE = (
    "# 本拼音库，拼音原始数据绝大多数由 pypinyin 生成，极小部分抓取自汉典网(zdic.net)。目前数据库中包含了 Unicode 17.0 版的汉字，且每个汉字的拼音数据都经过了多轮人工校对和修正。强调说明，为便按照一字一音原则编码输入单字双音汉字，这类汉字字音只取一个音节列入拼音候选列表。"
)


def normalize_pinyin_candidate(value: str) -> str:
    value = unicodedata.normalize("NFC", value.strip())
    if not value:
        return value
    chars = [BREVE_TO_CARON.get(ch, ch) for ch in value]
    value = "".join(chars)
    return unicodedata.normalize("NFC", value)


def parse_unicode_hanzi_file(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    lines: list[str] = path.read_text(encoding="utf-8").splitlines()
    header_lines: list[str] = []
    data_start = 0
    for index, line in enumerate(lines):
        if line.startswith("codepoint\t"):
            data_start = index
            break
        header_lines.append(line)

    if data_start >= len(lines):
        raise ValueError(f"unable to find header row in {path}")

    rows: list[dict[str, str]] = []
    reader = csv.DictReader(lines[data_start:], delimiter="\t")
    for row in reader:
        rows.append(row)
    return header_lines, rows


def parse_pinyin_source(path: Path) -> dict[str, list[str]]:
    pinyin_map: dict[str, list[str]] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if "#" in line:
            line = line.split("#", 1)[0].rstrip()
        if not line:
            continue

        if ":" not in line:
            continue

        codepoint, pinyin_text = line.split(":", 1)
        codepoint = codepoint.strip().upper()
        if not codepoint.startswith("U+"):
            continue

        pinyin_list = [normalize_pinyin_candidate(p) for p in parse_pinyin_list(pinyin_text)]
        if not pinyin_list:
            continue

        existing = pinyin_map.setdefault(codepoint, [])
        for p in pinyin_list:
            if p not in existing:
                existing.append(p)
    return pinyin_map


def parse_pinyin_list(raw: str) -> list[str]:
    raw = raw.strip()
    if raw.startswith('"') and raw.endswith('"'):
        raw = raw[1:-1]
    raw = raw.strip()
    if not raw:
        return []
    items = [normalize_pinyin_candidate(item.strip()) for item in raw.split(",") if item.strip()]
    return items


def merge_pinyins(existing: list[str], additions: Iterable[str]) -> list[str]:
    # Normalize inputs and preserve order, deduplicate
    def norm(s: str) -> str:
        return normalize_pinyin_candidate(s)

    result: list[str] = []
    seen: set[str] = set()
    for p in existing:
        np = norm(p)
        if np not in seen:
            seen.add(np)
            result.append(np)
    for p in additions:
        np = norm(p)
        if np not in seen:
            seen.add(np)
            result.append(np)
    return result


def strip_tone_marks(value: str) -> str:
    normalized = normalize_pinyin_candidate(value)
    decomposed = unicodedata.normalize("NFD", normalized)
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return unicodedata.normalize("NFC", stripped)


def has_tonal_equivalent(plain_untoned: str, candidates: Iterable[str]) -> bool:
    plain_norm = normalize_pinyin_candidate(plain_untoned)
    for candidate in candidates:
        candidate_norm = normalize_pinyin_candidate(candidate)
        if any(char in TONE_MARK_CHARS for char in candidate_norm):
            if strip_tone_marks(candidate_norm) == plain_norm:
                return True
    return False


def filter_nonstandard_candidates(
    candidates: Iterable[str],
    valid_plain_untoned: set[str],
    valid_numeric: set[str],
) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for p in candidates:
        normalized = normalize_pinyin_candidate(p)
        if not normalized:
            continue
        if not any(char in TONE_MARK_CHARS for char in normalized):
            if is_nonstandard_pinyin(normalized, valid_plain_untoned):
                continue
            if has_tonal_equivalent(normalized, candidates):
                continue
        elif is_toned_but_outside_codebook(normalized, valid_numeric):
            continue
        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def is_multi_syllable_pinyin(value: str) -> bool:
    return len(re.findall(r"[āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ]", value)) > 1


def apply_special_single_syllable_policy(codepoint: str, candidates: list[str]) -> list[str]:
    if codepoint not in SPECIAL_SINGLE_SYLLABLE_PY:
        return candidates

    chosen = SPECIAL_SINGLE_SYLLABLE_PY[codepoint]
    return [chosen]


def add_header_note_if_missing(header_lines: list[str]) -> list[str]:
    if any(HEADER_NOTE in line for line in header_lines):
        return header_lines
    result: list[str] = []
    inserted = False
    for line in header_lines:
        if not inserted and line.startswith("codepoint"):
            result.append(HEADER_NOTE)
            inserted = True
        result.append(line)
    if not inserted:
        result.append(HEADER_NOTE)
    return result


def load_valid_plain_untoned_pinyin(path: Path) -> set[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        key[:-1]
        for key in payload.keys()
        if isinstance(key, str) and key and key[-1] in "12345"
    }


def load_valid_numeric_pinyin(path: Path) -> set[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {key for key in payload.keys() if isinstance(key, str)}


def is_toned_but_outside_codebook(value: str, valid_numeric: set[str]) -> bool:
    if not any(char in TONE_MARK_CHARS for char in value):
        return False
    return marked_syllable_to_numeric(value) not in valid_numeric


def is_nonstandard_pinyin(value: str, valid_plain_untoned: set[str]) -> bool:
    value = normalize_pinyin_candidate(value)
    if any(char in TONE_MARK_CHARS for char in value):
        return False
    return value not in valid_plain_untoned


def write_unicode_hanzi_file(path: Path, header_lines: list[str], rows: list[dict[str, str]]) -> None:
    from io import StringIO

    buffer = StringIO()
    writer = csv.writer(buffer, delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(["codepoint", "hanzi", "pinyin", "pinyin_candidates"])
    for row in rows:
        writer.writerow([
            row["codepoint"],
            row["hanzi"],
            row.get("pinyin", ""),
            row.get("pinyin_candidates", ""),
        ])

    content = []
    content.extend(header_lines)
    if not any(line.startswith("codepoint") for line in header_lines):
        content.append("codepoint\thanzi\tpinyin\tpinyin_candidates")
    content.append(buffer.getvalue().rstrip("\n"))
    path.write_text("\n".join(content) + "\n", encoding="utf-8")


def build_report(changes: list[tuple[str, str, list[str]]]) -> str:
    lines = [
        f"updated_rows: {len(changes)}",
        "" if not changes else "examples:",
    ]
    for codepoint, hanzi, added in changes[:20]:
        lines.append(f"{codepoint} {hanzi}: added {added}")
    return "\n".join(line for line in lines if line)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Merge missing pinyin candidates from external pinyin sources into external_data/unicode_hanzi.txt."
    )
    parser.add_argument(
        "--target",
        default=str(Path(__file__).resolve().parents[2] / "external_data" / "unicode_hanzi.txt"),
        help="Target unicode_hanzi.txt file to update",
    )
    parser.add_argument(
        "--pinyin",
        default=str(Path("C:/dev/pinyin-data/pinyin.txt")),
        help="Source pinyin.txt file path",
    )
    parser.add_argument(
        "--zdic",
        default=str(Path("C:/dev/pinyin-data/zdic.txt")),
        help="Source zdic.txt file path",
    )
    parser.add_argument(
        "--pinyin-normalized",
        default=str(Path(__file__).resolve().parents[2] / "internal_data" / "pinyin_source_db" / "lexicon_exports" / "pinyin_normalized.json"),
        help="Validated pinyin_normalized.json path used to identify valid plain untoned pinyin",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not write back changes, only report differences",
    )
    args = parser.parse_args()

    target_path = Path(args.target)
    if not target_path.exists():
        raise FileNotFoundError(f"target file not found: {target_path}")

    normalized_path = Path(args.pinyin_normalized)
    if not normalized_path.exists():
        raise FileNotFoundError(f"pinyin_normalized.json not found: {normalized_path}")
    valid_plain_untoned = load_valid_plain_untoned_pinyin(normalized_path)
    valid_numeric = load_valid_numeric_pinyin(normalized_path)

    header_lines, rows = parse_unicode_hanzi_file(target_path)
    pinyin_map = parse_pinyin_source(Path(args.pinyin))
    zdic_map = parse_pinyin_source(Path(args.zdic))

    report_changes: list[tuple[str, str, list[str]]] = []
    target_by_codepoint = {row["codepoint"].upper(): row for row in rows}

    for codepoint, row in target_by_codepoint.items():
        raw_candidates = row.get("pinyin_candidates", "")
        if raw_candidates.strip():
            try:
                raw_existing_candidates = json.loads(raw_candidates)
            except json.JSONDecodeError:
                raw_existing_candidates = []
        else:
            raw_existing_candidates = []

        # normalize and remove existing nonstandard plain untoned values
        existing_candidates = filter_nonstandard_candidates(
            raw_existing_candidates,
            valid_plain_untoned,
            valid_numeric,
        )

        # gather additions from external sources, excluding nonstandard plain untoned values
        additions: list[str] = []
        for source_map in (pinyin_map, zdic_map):
            source_candidates = source_map.get(codepoint, [])
            source_candidates = filter_nonstandard_candidates(
                source_candidates,
                valid_plain_untoned,
                valid_numeric,
            )
            for p in source_candidates:
                if p not in additions:
                    additions.append(p)

        # merge will normalize and deduplicate existing + additions
        merged_candidates = merge_pinyins(existing_candidates, additions)
        merged_candidates = apply_special_single_syllable_policy(codepoint, merged_candidates)

        # normalize primary pinyin if present
        primary = row.get("pinyin", "") or ""
        primary_norm = normalize_pinyin_candidate(primary)
        if is_nonstandard_pinyin(primary_norm, valid_plain_untoned):
            primary_norm = ""
        if codepoint in SPECIAL_SINGLE_SYLLABLE_PY:
            primary_norm = SPECIAL_SINGLE_SYLLABLE_PY[codepoint]

        # determine if there is any effective change (normalization, additions, or cleanup of invalid candidates)
        existing_norm = [normalize_pinyin_candidate(p) for p in raw_existing_candidates]
        if merged_candidates != existing_norm or (primary and primary_norm != primary):
            # update row with normalized/merged candidates
            row["pinyin_candidates"] = json.dumps(merged_candidates, ensure_ascii=False)
            if not primary_norm and merged_candidates:
                row["pinyin"] = merged_candidates[0]
            else:
                row["pinyin"] = primary_norm

            # report what was added compared to normalized existing
            added = [p for p in merged_candidates if p not in existing_norm]
            report_changes.append((codepoint, row.get("hanzi", ""), added))

    if report_changes:
        if not args.dry_run:
            header_lines = add_header_note_if_missing(header_lines)
            write_unicode_hanzi_file(target_path, header_lines, rows)
        print(build_report(report_changes))
    else:
        print("no new pinyin candidates found")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
