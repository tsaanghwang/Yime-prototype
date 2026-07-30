"""Report source-attested syllables absent from the materialized inventory."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from syllable.codec.yinjie_encoder import YinjieEncoder
from yime.lexicon_bundle.syllable_admission import (
    DEFAULT_ADMISSION_PATH,
    load_syllable_admissions,
)

DEFAULT_DB = ROOT / ".generated" / "lexicon_source_bundle" / "source_lexicon.sqlite3"
DEFAULT_INVENTORY = ROOT / "yime" / "pinyin_normalized.json"
DEFAULT_OUTPUT = (
    ROOT / "internal_data" / "pinyin_source_db" / "missing_source_syllable_review.md"
)
PREFIX = "outside_current_decoder_inventory:"
SCOPE_PREFIX = "reviewed_syllable_scope_exclusion:"


def _formal_encoder_accepts(numeric: str) -> tuple[bool, str]:
    try:
        YinjieEncoder().encode_single_yinjie(numeric)
    except Exception as exc:  # audit must preserve the exact formal failure
        return False, f"{type(exc).__name__}: {exc}"
    return True, "formal encoder accepted"


def build_report(db_path: Path, inventory_path: Path, admission_path: Path) -> str:
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    admissions = load_syllable_admissions(admission_path)
    missing: dict[str, list[tuple[str, str, str, int]]] = defaultdict(list)
    accepted_counts: dict[str, int] = defaultdict(int)
    with sqlite3.connect(db_path) as connection:
        for source, source_file, text, reading, reason, frequency in connection.execute(
            """
            SELECT r.source, r.source_file, r.text, r.reading, r.reason,
                   COALESCE(b.frequency, 0)
            FROM rejections r
            LEFT JOIN bcc_frequency b ON b.text = r.text
            WHERE r.reason LIKE ? OR r.reason LIKE ?
            ORDER BY COALESCE(b.frequency, 0) DESC, r.text
            """,
            (PREFIX + "%", SCOPE_PREFIX + "%"),
        ):
            reason_text = str(reason)
            prefix = PREFIX if reason_text.startswith(PREFIX) else SCOPE_PREFIX
            for numeric in reason_text[len(prefix):].split(","):
                missing[numeric].append(
                    (str(source), str(source_file), str(text), str(reading), int(frequency))
                )
        for numeric_reading, count in connection.execute(
            "SELECT numeric, COUNT(*) FROM accepted_readings GROUP BY numeric"
        ):
            tokens = set(str(numeric_reading).split())
            for numeric in admissions:
                if numeric in tokens:
                    accepted_counts[numeric] += int(count)

    reviewed = sorted(set(missing) | set(admissions))
    lines = [
        "# 有来源但尚未进入当前音节库的拼音审查",
        "",
        "本报告从统一来源库的真实拒绝记录生成。非轻声音节须经逐项审查登记；有来源的无调音节按轻声正词法规则处理，不在本表逐项枚举。音元编码仍由正式编码器生成，不在此处手写。",
        "",
        "| 拼音 | 当前音节库 | 审查 | 范围 | 正式编码器 | 当前拒绝实例 | 重建后已接纳实例 |",
        "|---|---|---|---|---|---:|---:|",
    ]
    for numeric in reviewed:
        admission = admissions.get(numeric)
        encoder_ok, encoder_note = _formal_encoder_accepts(numeric)
        lines.append(
            "| {numeric} | {inventory} | {status} | {scope} | {encoder} | {rejected} | {accepted} |".format(
                numeric=numeric,
                inventory="已有" if numeric in inventory else "缺失",
                status=admission.status if admission else "未审查",
                scope=admission.scope if admission else "—",
                encoder="通过" if encoder_ok else "失败",
                rejected=len(missing.get(numeric, ())),
                accepted=accepted_counts.get(numeric, 0),
            )
        )
        if not encoder_ok:
            lines.append(f"  - 编码失败：`{encoder_note}`")

    lines.extend(["", "## BCC 高频与来源实例", ""])
    for numeric in reviewed:
        rows = missing.get(numeric, [])
        admission = admissions.get(numeric)
        lines.append(f"### `{numeric}`")
        if admission:
            lines.append(f"审查依据：{admission.decision_basis}")
        if rows:
            lines.append("")
            lines.append("| BCC 频次 | 条目 | 来源注音 | 来源 |")
            lines.append("|---:|---|---|---|")
            for source, source_file, text, reading, frequency in rows[:10]:
                lines.append(
                    f"| {frequency} | {text} | `{reading}` | {source}: `{Path(source_file).name}` |"
                )
        else:
            lines.append("")
            lines.append("当前统一来源库中已无该音节造成的门禁拒绝；审查证据保留在登记文件中。")
        lines.append("")

    lines.extend(
        [
            "## 不属于音节库扩充的拒绝",
            "",
            "格式错误、字符污染、音节数不匹配和未准入拼式仍由第一轮来源门禁拒绝；本流程不会用审查登记绕过这些错误。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--admissions", type=Path, default=DEFAULT_ADMISSION_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = build_report(args.db, args.inventory, args.admissions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
