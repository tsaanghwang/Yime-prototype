"""Streaming parsers for Yime's external lexicon evidence."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass(frozen=True)
class ReadingRecord:
    text: str
    reading: str
    source: str
    source_file: str
    line_number: int
    source_rank: int
    source_weight: int | None = None
    source_primary: bool = False
    codepoint_context: bool = False


@dataclass(frozen=True)
class FrequencyRecord:
    text: str
    frequency: int
    source_file: str
    line_number: int


def _dict_rows(path: Path) -> Iterator[tuple[int, dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        header: list[str] | None = None
        for line_number, raw_line in enumerate(stream, start=1):
            if raw_line.startswith("#") or not raw_line.strip():
                continue
            values = next(csv.reader([raw_line], delimiter="\t"))
            if header is None:
                header = [value.strip() for value in values]
                continue
            row = {
                key: (values[index].strip() if index < len(values) else "")
                for index, key in enumerate(header)
            }
            yield line_number, row


def iter_unihan_readings(path: Path) -> Iterator[ReadingRecord]:
    for line_number, row in _dict_rows(path):
        text = row.get("hanzi", "")
        common = row.get("common_reading", "")
        readings = [item.strip() for item in row.get("readings", "").split(",") if item.strip()]
        ordered = list(dict.fromkeys(([common] if common else []) + readings))
        for index, reading in enumerate(ordered):
            yield ReadingRecord(
                text=text,
                reading=reading,
                source="unihan",
                source_file=str(path),
                line_number=line_number,
                source_rank=10,
                source_primary=index == 0,
                codepoint_context=True,
            )


def iter_pypinyin_phrase_readings(path: Path) -> Iterator[ReadingRecord]:
    for line_number, row in _dict_rows(path):
        text = row.get("phrase", "")
        common = row.get("common_reading", "")
        readings = [item.strip() for item in row.get("readings", "").split("|") if item.strip()]
        ordered = list(dict.fromkeys(([common] if common else []) + readings))
        for index, reading in enumerate(ordered):
            yield ReadingRecord(
                text=text,
                reading=reading,
                source="pypinyin",
                source_file=str(path),
                line_number=line_number,
                source_rank=10,
                source_primary=index == 0,
            )


def iter_wanxiang_readings(path: Path, *, source_rank: int = 30) -> Iterator[ReadingRecord]:
    in_body = False
    with path.open("r", encoding="utf-8-sig") as stream:
        for line_number, raw_line in enumerate(stream, start=1):
            line = raw_line.rstrip("\r\n")
            if not in_body:
                if line.strip() == "...":
                    in_body = True
                continue
            if not line or line.startswith("#"):
                continue
            fields = line.split("\t")
            if len(fields) < 2:
                continue
            text, reading = fields[0].strip(), fields[1].strip()
            weight: int | None = None
            if len(fields) >= 3:
                try:
                    weight = int(fields[2].strip())
                except ValueError:
                    weight = None
            yield ReadingRecord(
                text=text,
                reading=reading,
                source="wanxiang",
                source_file=str(path),
                line_number=line_number,
                source_rank=source_rank,
                source_weight=weight,
            )


def iter_bcc_frequencies(path: Path) -> Iterator[FrequencyRecord]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        for line_number, row in enumerate(reader, start=1):
            if line_number == 1 and row and row[0].strip().lower() in {"word", "char"}:
                continue
            if len(row) < 2:
                continue
            text = row[0].strip()
            try:
                frequency = int(row[1].strip())
            except ValueError:
                continue
            if text:
                yield FrequencyRecord(text, frequency, str(path), line_number)
