# -*- coding: utf-8 -*-
"""
从 2024年新大纲普通话考试-儿化音词.pdf 重新提取韵母变化规则,
刷新 psc_outline_ocr.sqlite3 的 erhua_categories 表。

已知 PDF 原文错误:
  - üe＞ü:er 应为 ün＞ü:er (合群儿 héqúnr,群 qún 韵母是 ün)
  - en＞Per / ong＞oPr（鼻化）中混入噪声字母 P,需清理

用法:
  python refresh_erhua_categories.py            # 默认执行
  python refresh_erhua_categories.py --dry-run  # 只预览不写库
"""
import argparse
import re
import sqlite3
import shutil
import json
import unicodedata
from pathlib import Path
from datetime import datetime, timezone
import pdfplumber

ROOT = Path(__file__).resolve().parent
PDF = ROOT / "2024年新大纲普通话考试-儿化音词.pdf"
DB = ROOT / "psc_outline_ocr.sqlite3"

# 页眉/装饰噪声字符(不会出现在规则中)
NOISE_CHARS = set("PA话通普言畅畅")

# 组合波浪号(鼻化标记)
TILDE = "\u0303"

# 已知 PDF 原文错误 → 正确值
KNOWN_FIXES = {
    "üe>ü:er": {"rule_nfc": "ün>ü:er", "base_final": "ün",
                "note": "PDF原文üe>ü:er误,合群儿héqúnr群qún韵母为ün非üe"},
}


def clean_noise(text: str) -> str:
    return "".join(c for c in text if c not in NOISE_CHARS)


def nfc_rule(raw: str) -> str:
    """rule_raw → rule_nfc:
    1. 全角＞→半角>, 全角（）→半角()
    2. i(前)→i[ɿ], i(后)→i[ʅ]
    3. (o)→o
    4. (鼻化)→删除,在 r 前字符上加 ◌̃
    """
    s = raw.replace("＞", ">").replace("（", "(").replace("）", ")")
    s = re.sub(r"\s+", "", s)
    nasalized = "(鼻化)" in s
    s = s.replace("(鼻化)", "")
    if ">" not in s:
        return s
    left, right = s.split(">", 1)
    left = left.replace("i(前)", "i[ɿ]").replace("i(后)", "i[ʅ]").replace("(o)", "o")
    if nasalized:
        idx = right.rfind("r")
        if idx > 0:
            right = right[:idx] + TILDE + right[idx:]
    return f"{left}>{right}"


def parse_rule(rule_nfc: str):
    """从 rule_nfc 提取 base, final, nasalized。
    鼻化通过 ◌̃ 标记判断。"""
    if ">" not in rule_nfc:
        return None
    left, right = rule_nfc.split(">", 1)
    nasalized = 1 if TILDE in right else 0
    return left.strip(), right.strip(), nasalized


def extract_rules_from_pdf():
    """从 PDF 提取规则,返回 list[dict]。"""
    rules = []
    rule_re = re.compile(r"([^\s＞>]{1,10})\s*([＞>])\s*([^\s（()]{1,8})")

    with pdfplumber.open(PDF) as pdf:
        for pno, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            for line in text.split("\n"):
                if "＞" not in line and ">" not in line:
                    continue
                cleaned = clean_noise(line)
                m = rule_re.search(cleaned)
                if not m:
                    continue
                left_raw = m.group(1)
                sep = m.group(2)
                right_raw = m.group(3)
                rest = cleaned[m.end():]
                nasalized = 1 if "鼻化" in rest else 0

                rule_raw = f"{left_raw}{sep}{right_raw}"
                if nasalized:
                    rule_raw += "（鼻化）"
                rule_nfc = nfc_rule(rule_raw)

                parsed = parse_rule(rule_nfc)
                if not parsed:
                    continue
                base_final, erhua_final, _ = parsed

                rules.append({
                    "page_number": pno,
                    "rule_raw": rule_raw,
                    "rule_nfc": rule_nfc,
                    "base_final": base_final,
                    "erhua_final": erhua_final,
                    "nasalized": nasalized,
                })
    return rules


def apply_known_fixes(rules):
    """对已知 PDF 原文错误应用修正。"""
    fixes_applied = []
    for r in rules:
        key = r["rule_nfc"]
        if key in KNOWN_FIXES:
            fix = KNOWN_FIXES[key]
            old = dict(r)
            r["rule_nfc"] = fix["rule_nfc"]
            r["base_final"] = fix["base_final"]
            parsed = parse_rule(r["rule_nfc"])
            if parsed:
                r["erhua_final"] = parsed[1]
            fixes_applied.append((old, r, fix["note"]))
    return fixes_applied


def refresh_database(rules, dry_run=False):
    """按 source_index 顺序 UPDATE erhua_categories。"""
    if dry_run:
        print("[dry-run] 不写库")
        return

    bak = DB.with_name(f"{DB.stem}.before_category_refresh.{datetime.now().strftime('%Y%m%d-%H%M%S')}{DB.suffix}")
    shutil.copy2(DB, bak)
    print(f"已备份: {bak}")

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    existing = {r["source_index"]: dict(r) for r in cur.execute(
        "SELECT * FROM erhua_categories ORDER BY source_index")}

    if len(rules) != len(existing):
        print(f"警告: PDF提取{len(rules)}条, 数据库{len(existing)}条, 数量不一致!")

    now = datetime.now(timezone.utc).isoformat()
    updated = 0
    for idx, rule in enumerate(rules, 1):
        if idx not in existing:
            print(f"  跳过: source_index={idx} 不在数据库中")
            continue
        before = existing[idx]
        changed_fields = {}
        for field in ("rule_nfc", "base_final", "erhua_final", "nasalized"):
            if before[field] != rule[field]:
                changed_fields[field] = (before[field], rule[field])

        if not changed_fields:
            continue

        cur.execute(
            "UPDATE erhua_categories SET rule_nfc=?, base_final=?, "
            "erhua_final=?, nasalized=? WHERE source_index=?",
            (rule["rule_nfc"], rule["base_final"],
             rule["erhua_final"], rule["nasalized"], idx)
        )

        prev_json = json.dumps({k: before[k] for k in changed_fields}, ensure_ascii=False)
        cur_json = json.dumps({k: v[1] for k, v in changed_fields.items()}, ensure_ascii=False)
        cur.execute(
            "INSERT INTO manual_review_history "
            "(document_id, table_number, source_index, action, previous_json, current_json, occurred_at_utc) "
            "VALUES (3, 0, ?, 'refresh_category', ?, ?, ?)",
            (idx, prev_json, cur_json, now)
        )
        updated += 1
        print(f"  更新 source_index={idx}: {before['rule_nfc']} → {rule['rule_nfc']}")
        for field, (old, new) in changed_fields.items():
            print(f"    {field}: {old!r} → {new!r}")

    con.commit()
    con.close()
    print(f"\n共更新 {updated} 条规则")


def main():
    parser = argparse.ArgumentParser(description="从 PDF 刷新 erhua_categories")
    parser.add_argument("--dry-run", action="store_true", help="只预览不写库")
    args = parser.parse_args()

    print(f"PDF: {PDF}")
    print(f"DB:  {DB}")

    rules = extract_rules_from_pdf()
    print(f"\n从 PDF 提取 {len(rules)} 条规则:")
    for i, r in enumerate(rules, 1):
        nas = "(鼻化)" if r["nasalized"] else ""
        print(f"  {i:>2}. {r['rule_nfc']:<18} base={r['base_final']:<8} final={r['erhua_final']:<6} {nas}")

    fixes = apply_known_fixes(rules)
    if fixes:
        print(f"\n应用 {len(fixes)} 条已知修正:")
        for old, new, note in fixes:
            print(f"  {old['rule_nfc']} → {new['rule_nfc']}  ({note})")

    print(f"\n最终 {len(rules)} 条规则(修正后):")
    for i, r in enumerate(rules, 1):
        nas = "(鼻化)" if r["nasalized"] else ""
        print(f"  {i:>2}. {r['rule_nfc']:<18} base={r['base_final']:<8} final={r['erhua_final']:<6} {nas}")

    refresh_database(rules, dry_run=args.dry_run)
    print("\n完成。")


if __name__ == "__main__":
    main()
