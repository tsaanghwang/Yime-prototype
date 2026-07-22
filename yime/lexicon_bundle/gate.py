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

from .syllable_admission import DEFAULT_ADMISSION_PATH, load_syllable_admissions

SOURCE_ATTESTED_NEUTRAL_RULE = "ORTH-SOURCE-ATTESTED-NEUTRAL"
DEFAULT_NEUTRAL_SOURCE_POLICY_PATH = (
    Path(__file__).resolve().parents[2]
    / "internal_data"
    / "pinyin_source_db"
    / "neutral_tone_source_policy.json"
)


def load_neutral_source_policy(path: Path) -> dict[str, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "neutral-tone-source-policy-v1":
        raise ValueError(f"unsupported neutral-tone source policy schema: {path}")
    default = str(payload.get("default_unmarked_interpretation", "ambiguous"))
    if default not in {"neutral", "ambiguous"}:
        raise ValueError(f"invalid default unmarked interpretation: {default}")
    result = {"*": default}
    for source, raw in payload.get("sources", {}).items():
        interpretation = str(raw.get("unmarked_interpretation", ""))
        if interpretation not in {"neutral", "ambiguous"}:
            raise ValueError(
                f"invalid unmarked interpretation for {source}: {interpretation}"
            )
        result[str(source)] = interpretation
    return result


@dataclass(frozen=True)
class GateResult:
    accepted: bool
    marked: str = ""
    numeric: str = ""
    rule_ids: tuple[str, ...] = ()
    reason: str = ""
    pronunciation_scope: str = "standalone"
    neutral_tone_positions: tuple[int, ...] = ()
    neutral_tone_status: str = "none"


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

    def __init__(
        self,
        inventory_path: Path,
        admission_path: Path | None = DEFAULT_ADMISSION_PATH,
        neutral_source_policy_path: Path = DEFAULT_NEUTRAL_SOURCE_POLICY_PATH,
    ) -> None:
        payload = json.loads(inventory_path.read_text(encoding="utf-8"))
        self._decodable = frozenset(str(key) for key in payload)
        self._marked_by_numeric = {
            str(key): str(value) for key, value in payload.items()
        }
        self._policy = load_policy()
        self._admissions = (
            load_syllable_admissions(admission_path) if admission_path is not None else {}
        )
        self._neutral_source_policy = load_neutral_source_policy(
            neutral_source_policy_path
        )

    @lru_cache(maxsize=8192)
    def _review(self, syllable: str, codepoint: str | None) -> SyllableReview:
        return review_syllable(syllable, self._policy, codepoint=codepoint)

    def admit(
        self,
        text: str,
        reading: str,
        *,
        codepoint_context: bool = False,
        source: str = "",
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

        neutral_positions = tuple(
            index
            for index, item in enumerate(reviews, start=1)
            if item.canonical_numeric.endswith("5")
        )
        source_marks_tone_completely = (
            self._neutral_source_policy.get(
                source, self._neutral_source_policy["*"]
            )
            == "neutral"
        )
        registry_context_only = any(
            item.canonical_numeric in self._admissions
            and self._admissions[item.canonical_numeric].scope == "word_context_only"
            for item in reviews
        )
        pronunciation_scope = (
            "word_context_only" if registry_context_only else "standalone"
        )
        neutral_status = (
            "attested_neutral"
            if neutral_positions and source_marks_tone_completely
            else "unmarked_ambiguous"
            if neutral_positions
            else "none"
        )

        scope_excluded = tuple(
            item.canonical_numeric
            for item in reviews
            if item.canonical_numeric in self._admissions
            and self._admissions[item.canonical_numeric].status == "approved"
            and not self._admissions[item.canonical_numeric].admits(text)
        )
        if scope_excluded:
            return GateResult(
                False,
                rule_ids=tuple(
                    dict.fromkeys(
                        self._admissions[numeric].rule_id for numeric in scope_excluded
                    )
                ),
                reason="reviewed_syllable_scope_exclusion:" + ",".join(scope_excluded),
            )

        undecodable = tuple(
            item.canonical_numeric
            for item in reviews
            if item.canonical_numeric not in self._decodable
            and not (
                len(text) > 1
                and source_marks_tone_completely
                and item.canonical_numeric.endswith("5")
            )
            and not (
                item.canonical_numeric in self._admissions
                and self._admissions[item.canonical_numeric].admits(text)
            )
        )
        if undecodable:
            return GateResult(
                False,
                rule_ids=tuple(dict.fromkeys(item.rule_id for item in reviews)),
                reason="outside_current_decoder_inventory:" + ",".join(undecodable),
            )

        admission_rules = tuple(
            self._admissions[item.canonical_numeric].rule_id
            for item in reviews
            if item.canonical_numeric not in self._decodable
            and item.canonical_numeric in self._admissions
            and self._admissions[item.canonical_numeric].admits(text)
        )
        neutral_rules = tuple(
            SOURCE_ATTESTED_NEUTRAL_RULE
            for item in reviews
            if item.canonical_numeric.endswith("5")
            and source_marks_tone_completely
        )
        return GateResult(
            True,
            marked=" ".join(
                self._marked_by_numeric[item.canonical_numeric]
                if item.canonical_numeric in self._marked_by_numeric
                else (
                    self._admissions[item.canonical_numeric].marked
                    if item.canonical_numeric in self._admissions
                    else item.canonical_marked
                )
                for item in reviews
            ),
            numeric=" ".join(item.canonical_numeric for item in reviews),
            rule_ids=tuple(
                dict.fromkeys(
                    [item.rule_id for item in reviews]
                    + list(admission_rules)
                    + list(neutral_rules)
                )
            ),
            pronunciation_scope=pronunciation_scope,
            neutral_tone_positions=neutral_positions,
            neutral_tone_status=neutral_status,
        )
