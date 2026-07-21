"""Admission gate between external reading sources and Yime decoding."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from yime.utils.dictionary_pinyin_compliance import (
    SyllableReview,
    load_policy,
    review_syllable,
)


@dataclass(frozen=True)
class GateResult:
    accepted: bool
    marked: str = ""
    numeric: str = ""
    rule_ids: tuple[str, ...] = ()
    reason: str = ""


def is_han_text(text: str) -> bool:
    """Return whether every code point is a CJK ideograph accepted by this bundle."""
    if not text:
        return False
    for char in text:
        value = ord(char)
        if char == "〇":
            continue
        if not (
            0x3400 <= value <= 0x4DBF
            or 0x4E00 <= value <= 0x9FFF
            or 0xF900 <= value <= 0xFAFF
            or 0x20000 <= value <= 0x2EE5F
            or 0x2F800 <= value <= 0x2FA1F
            or 0x30000 <= value <= 0x323AF
        ):
            return False
    return True


class ReadingGate:
    """Apply the shared dictionary gate and require current decoder coverage."""

    def __init__(self, inventory_path: Path) -> None:
        payload = json.loads(inventory_path.read_text(encoding="utf-8"))
        self._decodable = frozenset(str(key) for key in payload)
        self._policy = load_policy()

    @lru_cache(maxsize=8192)
    def _review(self, syllable: str, codepoint: str | None) -> SyllableReview:
        return review_syllable(syllable, self._policy, codepoint=codepoint)

    def admit(
        self,
        text: str,
        reading: str,
        *,
        codepoint_context: bool = False,
    ) -> GateResult:
        if not is_han_text(text):
            return GateResult(False, reason="text_not_all_han")

        syllables = tuple(part for part in reading.strip().split() if part)
        if len(syllables) != len(text):
            return GateResult(
                False,
                reason=f"syllable_count_mismatch:{len(syllables)}!={len(text)}",
            )

        codepoint = f"U+{ord(text):04X}" if codepoint_context and len(text) == 1 else None
        reviews = tuple(self._review(syllable, codepoint) for syllable in syllables)
        rejected = tuple(item for item in reviews if not item.accepted)
        if rejected:
            first = rejected[0]
            return GateResult(
                False,
                rule_ids=tuple(dict.fromkeys(item.rule_id for item in rejected)),
                reason=f"{first.status}:{first.reason}",
            )

        undecodable = tuple(
            item.canonical_numeric
            for item in reviews
            if item.canonical_numeric not in self._decodable
        )
        if undecodable:
            return GateResult(
                False,
                rule_ids=tuple(dict.fromkeys(item.rule_id for item in reviews)),
                reason="outside_current_decoder_inventory:" + ",".join(undecodable),
            )

        return GateResult(
            True,
            marked=" ".join(item.canonical_marked for item in reviews),
            numeric=" ".join(item.canonical_numeric for item in reviews),
            rule_ids=tuple(dict.fromkeys(item.rule_id for item in reviews)),
        )
