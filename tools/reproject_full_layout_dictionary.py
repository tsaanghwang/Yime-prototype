"""Reproject an audited fixed-length dictionary after a layout-only change.

The selection and weights remain byte-for-byte equivalent at the record level;
only four-key syllable chunks are translated through old/new audited Pinyin
code maps.  This path is intentionally separate from candidate selection.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_pinyin_codes(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8", newline="") as stream:
        rows = csv.DictReader(stream, delimiter="\t")
        if rows.fieldnames != ["pinyin_tone", "full"]:
            raise ValueError(f"unexpected Pinyin code columns in {path}: {rows.fieldnames}")
        return {str(row["pinyin_tone"]): str(row["full"]) for row in rows}


def build_chunk_projection(old_codes: dict[str, str], new_codes: dict[str, str]) -> dict[str, str]:
    if set(old_codes) != set(new_codes):
        missing = sorted(set(old_codes) - set(new_codes))[:10]
        extra = sorted(set(new_codes) - set(old_codes))[:10]
        raise ValueError(f"Pinyin inventories differ: missing={missing}, extra={extra}")

    projection: dict[str, str] = {}
    for pinyin_tone in sorted(old_codes):
        old_code = old_codes[pinyin_tone]
        new_code = new_codes[pinyin_tone]
        if len(old_code) != 4 or len(new_code) != 4:
            raise ValueError(f"non-four-key syllable code: {pinyin_tone}")
        previous = projection.setdefault(old_code, new_code)
        if previous != new_code:
            raise ValueError(
                f"ambiguous old code {old_code!r}: {previous!r} versus {new_code!r}"
            )
    return projection


def reproject_code(code: str, projection: dict[str, str]) -> str:
    if len(code) % 4:
        raise ValueError(f"full code length is not divisible by four: {code!r}")
    chunks = [code[index : index + 4] for index in range(0, len(code), 4)]
    try:
        return "".join(projection[chunk] for chunk in chunks)
    except KeyError as exc:
        raise ValueError(f"unknown old full-code chunk: {exc.args[0]!r}") from exc


def reproject_selection(source: Path, destination: Path, projection: dict[str, str]) -> tuple[int, int]:
    total = 0
    changed = 0
    with source.open(encoding="utf-8", newline="") as input_stream, destination.open(
        "w", encoding="utf-8", newline=""
    ) as output_stream:
        reader = csv.DictReader(input_stream, delimiter="\t")
        if not reader.fieldnames or "full_layout_code" not in reader.fieldnames:
            raise ValueError("selection TSV has no full_layout_code column")
        writer = csv.DictWriter(
            output_stream,
            fieldnames=reader.fieldnames,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in reader:
            old_code = str(row["full_layout_code"])
            new_code = reproject_code(old_code, projection)
            row["full_layout_code"] = new_code
            writer.writerow(row)
            total += 1
            changed += old_code != new_code
    return total, changed


def reproject_reverse_source(source: Path, destination: Path, projection: dict[str, str]) -> tuple[int, int]:
    total = 0
    changed = 0
    with source.open(encoding="utf-8", newline="") as input_stream, destination.open(
        "w", encoding="utf-8", newline=""
    ) as output_stream:
        reader = csv.DictReader(input_stream, delimiter="\t")
        if not reader.fieldnames or "source_full_code" not in reader.fieldnames:
            raise ValueError("reverse source TSV has no source_full_code column")
        writer = csv.DictWriter(
            output_stream,
            fieldnames=reader.fieldnames,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in reader:
            old_code = str(row["source_full_code"])
            new_code = reproject_code(old_code, projection)
            row["source_full_code"] = new_code
            writer.writerow(row)
            total += 1
            changed += old_code != new_code
    return total, changed


def reproject_dictionary(source: Path, destination: Path, projection: dict[str, str]) -> tuple[int, int]:
    total = 0
    changed = 0
    with source.open(encoding="utf-8") as input_stream, destination.open(
        "w", encoding="utf-8", newline="\n"
    ) as output_stream:
        for line_number, line in enumerate(input_stream, start=1):
            stripped = line.rstrip("\r\n")
            if not stripped or stripped.startswith("#") or "\t" not in stripped:
                output_stream.write(stripped + "\n")
                continue
            fields = stripped.split("\t")
            if len(fields) < 3:
                raise ValueError(f"invalid dictionary row at line {line_number}")
            old_code = fields[1]
            fields[1] = reproject_code(old_code, projection)
            output_stream.write("\t".join(fields) + "\n")
            total += 1
            changed += old_code != fields[1]
    return total, changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dictionary", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--old-pinyin-codes", type=Path, required=True)
    parser.add_argument("--new-pinyin-codes", type=Path, required=True)
    parser.add_argument("--layout-digest", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--reverse-source", type=Path)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    dictionary_output = args.output_dir / args.dictionary.name
    selection_output = args.output_dir / args.selection.name
    manifest_output = args.output_dir / args.manifest.name
    reverse_output = args.output_dir / args.reverse_source.name if args.reverse_source else None

    projection = build_chunk_projection(
        load_pinyin_codes(args.old_pinyin_codes),
        load_pinyin_codes(args.new_pinyin_codes),
    )
    selection_rows, selection_changed = reproject_selection(
        args.selection, selection_output, projection
    )
    dictionary_rows, dictionary_changed = reproject_dictionary(
        args.dictionary, dictionary_output, projection
    )
    if selection_rows != dictionary_rows:
        raise ValueError(
            f"selection/dictionary row counts differ: {selection_rows} != {dictionary_rows}"
        )

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if int(manifest.get("total_reading_entries", -1)) != dictionary_rows:
        raise ValueError("manifest reading count does not match reprojected dictionary")
    manifest["output_dictionary"] = str(dictionary_output.resolve())
    manifest["output_sha256"] = sha256(dictionary_output)
    manifest["selection_tsv"] = str(selection_output.resolve())
    manifest["selection_tsv_sha256"] = sha256(selection_output)
    reverse_rows = 0
    reverse_changed = 0
    if args.reverse_source and reverse_output:
        reverse_rows, reverse_changed = reproject_reverse_source(
            args.reverse_source, reverse_output, projection
        )

    manifest["layout_reprojection"] = {
        "layout_digest": args.layout_digest,
        "old_pinyin_codes_sha256": sha256(args.old_pinyin_codes),
        "new_pinyin_codes_sha256": sha256(args.new_pinyin_codes),
        "record_count": dictionary_rows,
        "changed_dictionary_records": dictionary_changed,
        "changed_selection_records": selection_changed,
        "reverse_source_rows": reverse_rows,
        "changed_reverse_source_rows": reverse_changed,
        "reverse_source_sha256": sha256(reverse_output) if reverse_output else "",
        "candidate_selection_changed": False,
        "weights_changed": False,
    }
    manifest_output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"records={dictionary_rows}")
    print(f"changed_dictionary_records={dictionary_changed}")
    print(f"changed_selection_records={selection_changed}")
    print(f"reverse_source_rows={reverse_rows}")
    print(f"changed_reverse_source_rows={reverse_changed}")
    print(f"dictionary={dictionary_output}")
    print(f"selection={selection_output}")
    print(f"manifest={manifest_output}")
    if reverse_output:
        print(f"reverse_source={reverse_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
