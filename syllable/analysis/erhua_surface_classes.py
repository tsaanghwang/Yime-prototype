"""Rule-driven surface-class normalization for the research-only erhua draft."""

from __future__ import annotations

import copy
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from syllable.analysis.erhua_final_review import (
    SEGMENT_NAMES,
    normalize_surface_segment,
    render_surface_segments,
)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(rendered, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def _entries(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for group in payload["finals"].values():
        for final, entry in group.items():
            if final in result:
                raise ValueError(f"草稿中的韵母键不唯一：{final}")
            result[str(final)] = entry
    return result


def _normalize_template(value: object) -> dict[str, dict[str, object]]:
    if not isinstance(value, Mapping) or set(value) != set(SEGMENT_NAMES):
        raise ValueError("表层类模板必须且只能包含呼音、主音、末音。")
    return {
        name: normalize_surface_segment(value[name])
        for name in SEGMENT_NAMES
    }


def _source_results(entry: Mapping[str, Any]) -> set[str]:
    return {
        str(source.get("source_erhua_final"))
        for source in entry.get("erhua_final") or []
        if source.get("source_erhua_final")
    }


def load_surface_class_rules(path: Path) -> dict[str, Any]:
    payload = _read_json(path)
    if payload.get("runtime_enabled") is not False:
        raise ValueError("儿化表层类规则必须保持 runtime_enabled=false。")
    classes = payload.get("classes")
    if not isinstance(classes, dict) or not classes:
        raise ValueError("儿化表层类规则缺少 classes。")
    seen_members: dict[str, str] = {}
    for class_id, rule in classes.items():
        rule["surface_segments"] = _normalize_template(rule.get("surface_segments"))
        members = [str(value) for value in rule.get("members") or []]
        if not members:
            raise ValueError(f"{class_id} 没有成员。")
        for member in members:
            if member in seen_members:
                raise ValueError(
                    f"韵母 {member} 同时属于 {seen_members[member]} 和 {class_id}。"
                )
            seen_members[member] = str(class_id)
    return payload


def apply_surface_class_rules(
    draft_path: Path,
    rules_path: Path,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    draft_path = Path(draft_path)
    rules_path = Path(rules_path)
    draft = _read_json(draft_path)
    if draft.get("runtime_enabled") is not False:
        raise ValueError("儿化草稿必须保持 runtime_enabled=false。")
    rules = load_surface_class_rules(rules_path)
    entries = _entries(draft)
    timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    changed: list[str] = []
    unchanged: list[str] = []

    for class_id, rule in rules["classes"].items():
        template = rule["surface_segments"]
        expected = {str(value) for value in rule.get("source_results") or []}
        aliases = rule.get("technical_aliases") or {}
        for member in rule["members"]:
            if member not in entries:
                raise ValueError(f"{class_id} 的成员不存在：{member}")
            entry = entries[member]
            actual = _source_results(entry)
            if actual != expected:
                raise ValueError(
                    f"{class_id}/{member} 的来源儿化结果为 {sorted(actual)}，"
                    f"与规则 {sorted(expected)} 不一致。"
                )
            review = entry.get("three_segment_review") or {}
            if int(review.get("schema_version") or 0) != 2:
                raise ValueError(f"{member} 尚未迁移到 structured segment schema。")
            normalized = copy.deepcopy(template)
            desired_ipa = render_surface_segments(normalized)
            desired_fields = {
                "surface_segments": normalized,
                "surface_ipa": desired_ipa,
                "surface_class": class_id,
                "surface_class_rule_version": int(rules["schema_version"]),
            }
            differs = any(review.get(key) != value for key, value in desired_fields.items())
            review.update(desired_fields)
            entry["erhua_surface_class"] = {
                "class_id": class_id,
                "rule_version": int(rules["schema_version"]),
                "basis": str(rule.get("basis") or ""),
                "technical_alias_of": str(aliases.get(member) or ""),
                "runtime_enabled": False,
            }
            if differs:
                review["revision"] = int(review.get("revision") or 0) + 1
                review["updated_utc"] = timestamp.isoformat().replace("+00:00", "Z")
                changed.append(member)
            else:
                unchanged.append(member)

    draft["erhua_surface_class_model"] = {
        "schema_version": int(rules["schema_version"]),
        "status": "research_draft_only",
        "rules_source": "external_data/tmp/erhua_surface_class_rules.json",
        "class_count": len(rules["classes"]),
        "member_count": sum(len(rule["members"]) for rule in rules["classes"].values()),
        "policy": str(rules.get("policy") or ""),
        "runtime_enabled": False,
    }
    refresh = draft.setdefault("draft_refresh", {})
    refresh.update(
        {
            "updated_utc": timestamp.isoformat().replace("+00:00", "Z"),
            "surface_class_rules_applied": True,
            "review_decisions_changed": False,
            "formal_final_styles_changed": False,
            "runtime_artifacts_changed": False,
        }
    )
    _write_json(draft_path, draft)
    return {
        "class_count": len(rules["classes"]),
        "changed_members": changed,
        "unchanged_members": unchanged,
    }


def audit_surface_classes(draft_path: Path, rules_path: Path) -> dict[str, Any]:
    draft = _read_json(draft_path)
    rules = load_surface_class_rules(rules_path)
    entries = _entries(draft)
    mismatches: list[str] = []
    class_rows: dict[str, dict[str, Any]] = {}
    for class_id, rule in rules["classes"].items():
        template = rule["surface_segments"]
        expected_ipa = render_surface_segments(template)
        members = []
        for member in rule["members"]:
            review = entries[member].get("three_segment_review") or {}
            if (
                review.get("surface_class") != class_id
                or review.get("surface_segments") != template
                or review.get("surface_ipa") != expected_ipa
            ):
                mismatches.append(member)
            members.append(member)
        class_rows[class_id] = {
            "members": members,
            "surface_ipa": expected_ipa,
            "surface_yime": render_surface_segments(
                template, notation="yime_combining_r"
            ),
        }
    return {"mismatches": mismatches, "classes": class_rows}


__all__ = [
    "apply_surface_class_rules",
    "audit_surface_classes",
    "load_surface_class_rules",
]
