"""Fail closed when a keyboard-layout change bypasses the semantic chain."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, cast


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from syllable.codec.yinjie_encoder import YinjieEncoder
from tools.resolve_manual_key_layout import build_resolved_layout
from yime.utils.yinyuan_id_chain import (
    encode_numeric_pinyin_to_yinyuan_ids,
    load_semantic_yinyuan_registry,
    load_symbol_to_yinyuan_id,
    load_yinyuan_id_to_layout_key,
    symbol_code_to_yinyuan_ids,
)


LOCK_PATH = Path("internal_data/layout_change_lock.json")
LAYOUT_PATH = Path("internal_data/manual_key_layout.json")
RESOLVED_LAYOUT_PATH = Path("internal_data/manual_key_layout.resolved.json")
CANONICAL_SYMBOL_PATH = Path("internal_data/key_to_symbol.json")
PINYIN_INVENTORY_PATH = Path(
    "internal_data/pinyin_source_db/lexicon_exports/pinyin_normalized.json"
)
YINJIE_CODE_PATH = Path("syllable/codec/yinjie_code.json")


def _load_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def semantic_registry_digest(repo_root: Path = ROOT) -> str:
    registry = load_semantic_yinyuan_registry(repo_root)
    protected_rows = [
        {
            "yinyuan_id": yinyuan_id,
            "category": entry["category"],
            "label": entry["label"],
            "semantic_code": entry["semantic_code"],
            "runtime_codepoint": f"U+{ord(entry['runtime_char']):04X}",
        }
        for yinyuan_id, entry in sorted(registry.items())
    ]
    serialized = json.dumps(
        protected_rows,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def pinyin_yinyuan_chain_digest(repo_root: Path = ROOT) -> str:
    """Digest every reviewed numeric-Pinyin -> four-Yinyuan-ID result."""
    inventory = _load_json(repo_root / PINYIN_INVENTORY_PATH)
    encoder = YinjieEncoder()
    protected_rows = [
        [
            pinyin_tone,
            *encode_numeric_pinyin_to_yinyuan_ids(
                pinyin_tone,
                repo_root=repo_root,
                encoder=encoder,
            ),
        ]
        for pinyin_tone in sorted(inventory)
    ]
    serialized = json.dumps(
        protected_rows,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _check_semantic_lock(repo_root: Path, lock: dict[str, Any], issues: list[str]) -> None:
    expected_digest = str(lock.get("semantic_registry_sha256") or "")
    actual_digest = semantic_registry_digest(repo_root)
    if actual_digest != expected_digest:
        issues.append(
            "semantic Yinyuan registry changed during a layout change: "
            f"expected {expected_digest}, got {actual_digest}. "
            "A semantic change requires a separate reviewed change, never a layout shortcut."
        )
    expected_chain_digest = str(lock.get("pinyin_yinyuan_chain_sha256") or "")
    actual_chain_digest = pinyin_yinyuan_chain_digest(repo_root)
    if actual_chain_digest != expected_chain_digest:
        issues.append(
            "numeric-Pinyin -> Yinyuan-ID semantics changed during a layout change: "
            f"expected {expected_chain_digest}, got {actual_chain_digest}. "
            "Do not update this digest as part of a keyboard-layout change."
        )


def _check_single_layout_source(repo_root: Path, lock: dict[str, Any], issues: list[str]) -> None:
    canonical = str(lock.get("canonical_layout_source") or "")
    if canonical != LAYOUT_PATH.as_posix():
        issues.append(f"lock names an unexpected canonical layout source: {canonical}")
    for relative in cast(list[str], lock.get("forbidden_parallel_layout_sources", [])):
        if (repo_root / relative).exists():
            issues.append(f"parallel layout source is forbidden: {relative}")

    try:
        mapping = load_yinyuan_id_to_layout_key(repo_root)
    except Exception as exc:
        issues.append(f"canonical layout is invalid: {exc}")
        return
    if "`" in mapping.values():
        issues.append("backtick must remain the single reserved base key")
    candidate_tokens = set("!@#$%^&*(")
    occupied_candidates = sorted(candidate_tokens & set(mapping.values()))
    if occupied_candidates:
        issues.append(
            "Shift+1 through Shift+9 are candidate actions, not Yinyuan keys: "
            + ", ".join(occupied_candidates)
        )


def _check_resolved_layout(repo_root: Path, issues: list[str]) -> None:
    layout = _load_json(repo_root / LAYOUT_PATH)
    symbols = cast(dict[str, str], _load_json(repo_root / CANONICAL_SYMBOL_PATH))
    expected = build_resolved_layout(layout, symbols)
    resolved_path = repo_root / RESOLVED_LAYOUT_PATH
    if not resolved_path.exists():
        issues.append(f"missing derived layout: {RESOLVED_LAYOUT_PATH.as_posix()}")
        return
    actual = _load_json(resolved_path)
    if actual != expected:
        issues.append(
            "manual_key_layout.resolved.json is stale; run the locked layout pipeline"
        )


def _check_full_pinyin_chain(repo_root: Path, issues: list[str]) -> None:
    inventory = _load_json(repo_root / PINYIN_INVENTORY_PATH)
    codebook = _load_json(repo_root / YINJIE_CODE_PATH)
    if set(inventory) != set(codebook):
        missing = sorted(set(inventory) - set(codebook))[:10]
        extra = sorted(set(codebook) - set(inventory))[:10]
        issues.append(f"pinyin inventory/codebook mismatch: missing={missing}, extra={extra}")
        return

    encoder = YinjieEncoder()
    for pinyin_tone in sorted(inventory):
        try:
            semantic_ids = encode_numeric_pinyin_to_yinyuan_ids(
                pinyin_tone,
                repo_root=repo_root,
                encoder=encoder,
            )
            stored_ids = symbol_code_to_yinyuan_ids(
                str(codebook[pinyin_tone]),
                repo_root=repo_root,
            )
        except Exception as exc:
            issues.append(f"numeric Pinyin chain failed for {pinyin_tone}: {exc}")
            if len(issues) >= 20:
                return
            continue
        mismatch = compare_pinyin_chain_entry(pinyin_tone, semantic_ids, stored_ids)
        if mismatch:
            issues.append(mismatch)
            if len(issues) >= 20:
                return


def compare_pinyin_chain_entry(
    pinyin_tone: str,
    semantic_ids: tuple[str, ...],
    stored_ids: tuple[str, ...],
) -> str:
    if semantic_ids == stored_ids:
        return ""
    return (
        f"middle-entry code detected for {pinyin_tone}: "
        f"semantic={semantic_ids}, stored={stored_ids}"
    )


def check_layout_change_lock(
    repo_root: Path = ROOT,
    *,
    include_derived_artifacts: bool = True,
) -> list[str]:
    lock = _load_json(repo_root / LOCK_PATH)
    issues: list[str] = []
    _check_semantic_lock(repo_root, lock, issues)
    _check_single_layout_source(repo_root, lock, issues)
    if include_derived_artifacts:
        _check_resolved_layout(repo_root, issues)
    _check_full_pinyin_chain(repo_root, issues)
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Enforce the numeric-Pinyin -> Yinyuan-ID -> canonical-layout chain."
    )
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--print-semantic-digest", action="store_true")
    parser.add_argument("--print-pinyin-chain-digest", action="store_true")
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Check protected semantics and canonical source before regenerating derived artifacts.",
    )
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    if args.print_semantic_digest:
        print(semantic_registry_digest(repo_root))
        return 0
    if args.print_pinyin_chain_digest:
        print(pinyin_yinyuan_chain_digest(repo_root))
        return 0
    issues = check_layout_change_lock(
        repo_root,
        include_derived_artifacts=not args.preflight,
    )
    if issues:
        print("layout change lock failed")
        for issue in issues:
            print(f"- {issue}")
        return 1
    print("layout change lock passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
