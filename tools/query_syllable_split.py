from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Sequence

from yime.asset_paths import resolve_source_pinyin_db_path


ROOT = Path(__file__).resolve().parent.parent
SOURCE_DB_PATH = resolve_source_pinyin_db_path(ROOT)

# cspell:ignore jqxy zcsr
APPROVED_RULE_MISMATCHES = {
    ("jqxy_u_to_umlaut", "jqx_umlaut_family"),
    ("jqxy_u_to_umlaut", "yu_umlaut_family"),
    ("zcsr_tongue_tip_i", "default_first_char"),
    ("zh_ch_sh_tongue_tip_i", "zh_ch_sh"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="查询 v_syllable_split_current_rule 上的音节前缀、异常分流和冲突音节。"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prefix_parser = subparsers.add_parser(
        "prefix",
        help="按原始数字标调音节前缀查询。",
    )
    prefix_parser.add_argument("prefix", help="音节前缀，例如 w、we、y、zh。")
    prefix_parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="最多显示多少条结果，默认 50。",
    )

    anomaly_parser = subparsers.add_parser(
        "anomaly",
        help="快速定位非默认分流音节；加 --strict 只看疑似异常。",
    )
    anomaly_parser.add_argument(
        "--strict",
        action="store_true",
        help="只显示疑似异常，排除当前已知且允许的 numeric/tone 规则差异。",
    )
    anomaly_parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="最多显示多少条结果，默认 100。",
    )

    conflict_parser = subparsers.add_parser(
        "conflict",
        help="快速定位 numeric_syllable -> marked_syllable 多映射冲突。",
    )
    conflict_parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="最多显示多少条结果，默认 100。",
    )

    return parser.parse_args()


def print_metadata(args: argparse.Namespace) -> None:
    print(f"command={args.command}")
    print(f"source_db={SOURCE_DB_PATH}")
    if hasattr(args, "limit"):
        print(f"limit={args.limit}")
    if args.command == "prefix":
        print(f"prefix={args.prefix}")
    if args.command == "anomaly":
        print(f"strict={args.strict}")


def print_section(title: str) -> None:
    print()
    print(title)
    print("-" * len(title))


def print_no_result() -> None:
    print("无结果")


def format_row(row: sqlite3.Row, columns: Sequence[str]) -> str:
    return " ".join(f"{column}={row[column]}" for column in columns)


def fetch_rows(
    connection: sqlite3.Connection,
    query: str,
    parameters: Sequence[object],
) -> list[sqlite3.Row]:
    return connection.execute(query, parameters).fetchall()


def query_prefix(connection: sqlite3.Connection, prefix: str, limit: int) -> None:
    print_section("音节前缀查询")
    rows = fetch_rows(
        connection,
        """
        SELECT
            original_numeric_syllable,
            original_marked_syllable,
            source_tables,
            flattened_row_count,
            current_rule_numeric_split,
            current_rule_tone_split,
            numeric_matched_rule,
            tone_matched_rule
        FROM v_syllable_split_current_rule
        WHERE original_numeric_syllable LIKE ?
        ORDER BY original_numeric_syllable, original_marked_syllable
        LIMIT ?
        """,
        (f"{prefix}%", limit),
    )
    if not rows:
        print_no_result()
        return
    for row in rows:
        print(
            format_row(
                row,
                (
                    "original_numeric_syllable",
                    "original_marked_syllable",
                    "source_tables",
                    "flattened_row_count",
                    "current_rule_numeric_split",
                    "current_rule_tone_split",
                    "numeric_matched_rule",
                    "tone_matched_rule",
                ),
            )
        )


def query_anomaly(connection: sqlite3.Connection, strict: bool, limit: int) -> None:
    print_section("异常音节快速定位")
    base_columns = (
        "original_numeric_syllable",
        "original_marked_syllable",
        "source_tables",
        "flattened_row_count",
        "current_rule_numeric_split",
        "current_rule_tone_split",
        "numeric_matched_rule",
        "tone_matched_rule",
    )
    if strict:
        approved = ", ".join("(?, ?)" for _ in APPROVED_RULE_MISMATCHES)
        parameters: list[object] = []
        for pair in sorted(APPROVED_RULE_MISMATCHES):
            parameters.extend(pair)
        parameters.append(limit)
        rows = fetch_rows(
            connection,
            f"""
            SELECT
                original_numeric_syllable,
                original_marked_syllable,
                source_tables,
                flattened_row_count,
                current_rule_numeric_split,
                current_rule_tone_split,
                numeric_matched_rule,
                tone_matched_rule
            FROM v_syllable_split_current_rule
            WHERE (
                numeric_matched_rule <> tone_matched_rule
                AND (numeric_matched_rule, tone_matched_rule) NOT IN ({approved})
            )
            OR TRIM(COALESCE(source_tables, '')) = ''
            OR TRIM(COALESCE(current_rule_initial, '')) = ''
            ORDER BY original_numeric_syllable, original_marked_syllable
            LIMIT ?
            """,
            parameters,
        )
        if not rows:
            print("无疑似异常；当前 numeric/tone 规则差异都落在已知允许集合内。")
            return
    else:
        rows = fetch_rows(
            connection,
            """
            SELECT
                original_numeric_syllable,
                original_marked_syllable,
                source_tables,
                flattened_row_count,
                current_rule_numeric_split,
                current_rule_tone_split,
                numeric_matched_rule,
                tone_matched_rule
            FROM v_syllable_split_current_rule
            WHERE numeric_matched_rule <> 'default_first_char'
               OR tone_matched_rule <> 'default_first_char'
            ORDER BY original_numeric_syllable, original_marked_syllable
            LIMIT ?
            """,
            (limit,),
        )
        if not rows:
            print_no_result()
            return
    for row in rows:
        print(format_row(row, base_columns))


def query_conflict(connection: sqlite3.Connection, limit: int) -> None:
    print_section("冲突音节快速定位")
    rows = fetch_rows(
        connection,
        """
        WITH split_context AS (
            SELECT
                original_numeric_syllable AS numeric_syllable,
                GROUP_CONCAT(DISTINCT original_marked_syllable) AS marked_rows,
                GROUP_CONCAT(DISTINCT current_rule_tone_split) AS tone_splits,
                GROUP_CONCAT(DISTINCT source_tables) AS source_tables
            FROM v_syllable_split_current_rule
            GROUP BY original_numeric_syllable
        )
        SELECT
            c.numeric_syllable,
            c.marked_variant_count,
            c.marked_syllable_variants,
            sc.tone_splits,
            sc.source_tables
        FROM v_numeric_syllable_marked_conflicts AS c
        LEFT JOIN split_context AS sc
          ON sc.numeric_syllable = c.numeric_syllable
        ORDER BY c.marked_variant_count DESC, c.numeric_syllable
        LIMIT ?
        """,
        (limit,),
    )
    if not rows:
        print("无冲突；当前没有 numeric_syllable 对应多个 marked_syllable 的记录。")
        return
    for row in rows:
        print(
            format_row(
                row,
                (
                    "numeric_syllable",
                    "marked_variant_count",
                    "marked_syllable_variants",
                    "tone_splits",
                    "source_tables",
                ),
            )
        )


def main() -> None:
    args = parse_args()
    print_metadata(args)
    with sqlite3.connect(SOURCE_DB_PATH) as connection:
        connection.row_factory = sqlite3.Row
        if args.command == "prefix":
            query_prefix(connection, args.prefix, args.limit)
        elif args.command == "anomaly":
            query_anomaly(connection, args.strict, args.limit)
        elif args.command == "conflict":
            query_conflict(connection, args.limit)
        else:
            raise ValueError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    main()
