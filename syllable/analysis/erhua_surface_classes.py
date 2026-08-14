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


def _ng_coda_surface_segments(entry: Mapping[str, Any]) -> dict[str, dict[str, object]]:
    review = entry.get("three_segment_review") or {}
    base_segments = review.get("base_segments") or {}
    if set(base_segments) != set(SEGMENT_NAMES):
        raise ValueError("-ng 鼻化类缺少完整的基础三段。")
    if str(base_segments["末音"]) != "ŋ":
        raise ValueError("-ng 鼻化类的基础末音必须是 ŋ。")
    main_quality = str(base_segments["主音"])
    return {
        "呼音": normalize_surface_segment(
            {
                "quality": str(base_segments["呼音"]),
                "features": {"rhotic": False, "nasalized": False},
            }
        ),
        "主音": normalize_surface_segment(
            {"quality": main_quality, "features": {"rhotic": True, "nasalized": True}}
        ),
        "末音": normalize_surface_segment(
            {"quality": main_quality, "features": {"rhotic": True, "nasalized": True}}
        ),
    }


def _surface_segments_for_member(
    rule: Mapping[str, Any], member: str, entry: Mapping[str, Any]
) -> dict[str, dict[str, object]]:
    transform = str(rule.get("transform") or "")
    if transform == "ng_coda_to_nasalized_rhotic_main":
        return _ng_coda_surface_segments(entry)
    if transform:
        raise ValueError(f"{member} 使用未知儿化表层变换：{transform}")
    return copy.deepcopy(rule["surface_segments"])


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
        transform = str(rule.get("transform") or "")
        if transform:
            if transform != "ng_coda_to_nasalized_rhotic_main":
                raise ValueError(f"{class_id} 使用未知儿化表层变换：{transform}")
            if "surface_segments" in rule:
                raise ValueError(f"{class_id} 不能同时定义 transform 和 surface_segments。")
        else:
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
    surface_changed: list[str] = []
    metadata_changed: list[str] = []
    stale_classifications_cleared: list[str] = []
    unchanged: list[str] = []

    active_members = {
        str(member)
        for rule in rules["classes"].values()
        for member in rule["members"]
    }
    for final, entry in entries.items():
        if final in active_members:
            continue
        review = entry.get("three_segment_review") or {}
        cleared = entry.pop("erhua_surface_class", None) is not None
        for field in ("surface_class", "surface_class_rule_version"):
            if field in review:
                review.pop(field)
                cleared = True
        if cleared:
            stale_classifications_cleared.append(final)

    for class_id, rule in rules["classes"].items():
        expected_by_member = rule.get("source_results_by_member") or {}
        expected = {str(value) for value in rule.get("source_results") or []}
        aliases = rule.get("technical_aliases") or {}
        for member in rule["members"]:
            if member not in entries:
                raise ValueError(f"{class_id} 的成员不存在：{member}")
            entry = entries[member]
            member_expected = {
                str(value) for value in expected_by_member.get(member, expected)
            }
            actual = _source_results(entry)
            if actual != member_expected:
                raise ValueError(
                    f"{class_id}/{member} 的来源儿化结果为 {sorted(actual)}，"
                    f"与规则 {sorted(member_expected)} 不一致。"
                )
            review = entry.get("three_segment_review") or {}
            if int(review.get("schema_version") or 0) != 2:
                raise ValueError(f"{member} 尚未迁移到 structured segment schema。")
            normalized = _surface_segments_for_member(rule, member, entry)
            desired_ipa = render_surface_segments(normalized)
            desired_fields = {
                "surface_segments": normalized,
                "surface_ipa": desired_ipa,
                "surface_class": class_id,
                "surface_class_rule_version": int(rules["schema_version"]),
            }
            surface_differs = any(
                review.get(key) != value
                for key, value in desired_fields.items()
                if key in {"surface_segments", "surface_ipa"}
            )
            metadata_differs = any(
                review.get(key) != value
                for key, value in desired_fields.items()
                if key in {"surface_class", "surface_class_rule_version"}
            )
            desired_entry_class = {
                "class_id": class_id,
                "rule_version": int(rules["schema_version"]),
                "basis": str(rule.get("basis") or ""),
                "technical_alias_of": str(aliases.get(member) or ""),
                "runtime_enabled": False,
            }
            entry_metadata_differs = entry.get("erhua_surface_class") != desired_entry_class
            review.update(desired_fields)
            entry["erhua_surface_class"] = desired_entry_class
            if surface_differs:
                review["revision"] = int(review.get("revision") or 0) + 1
                review["updated_utc"] = timestamp.isoformat().replace("+00:00", "Z")
                surface_changed.append(member)
            elif metadata_differs or entry_metadata_differs:
                metadata_changed.append(member)
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
        "changed_members": surface_changed + metadata_changed,
        "surface_changed_members": surface_changed,
        "metadata_changed_members": metadata_changed,
        "stale_classifications_cleared": stale_classifications_cleared,
        "unchanged_members": unchanged,
    }


def audit_surface_classes(draft_path: Path, rules_path: Path) -> dict[str, Any]:
    draft = _read_json(draft_path)
    rules = load_surface_class_rules(rules_path)
    entries = _entries(draft)
    mismatches: list[str] = []
    class_rows: dict[str, dict[str, Any]] = {}
    for class_id, rule in rules["classes"].items():
        members = []
        member_surfaces: dict[str, str] = {}
        for member in rule["members"]:
            template = _surface_segments_for_member(rule, member, entries[member])
            expected_ipa = render_surface_segments(template)
            review = entries[member].get("three_segment_review") or {}
            if (
                review.get("surface_class") != class_id
                or review.get("surface_segments") != template
                or review.get("surface_ipa") != expected_ipa
            ):
                mismatches.append(member)
            members.append(member)
            member_surfaces[member] = expected_ipa
        unique_surfaces = list(dict.fromkeys(member_surfaces.values()))
        class_row = {
            "members": members,
            "surface_ipa": unique_surfaces[0] if len(unique_surfaces) == 1 else "按成员基础主音派生",
            "surface_yime": (
                render_surface_segments(template, notation="yime_combining_r")
                if len(unique_surfaces) == 1
                else "按成员基础主音派生"
            ),
        }
        if rule.get("transform"):
            class_row["member_surfaces"] = member_surfaces
        class_rows[class_id] = class_row
    return {"mismatches": mismatches, "classes": class_rows}


__all__ = [
    "apply_surface_class_rules",
    "audit_surface_classes",
    "load_surface_class_rules",
]
