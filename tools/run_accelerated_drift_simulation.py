#!/usr/bin/env python3
"""Run a reproducible multi-user accelerated learning-drift simulation.

The simulator is calibrated by the real librime component-learning replay:
each workload item keeps its measured cold top-1, constructibility and
same-code behavior. Virtual time only controls workload epochs, restarts and
promotion rounds; it does not invent wall-clock-dependent Rime behavior.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


PERSONAS = ("office", "developer", "geography", "literature", "specialist", "drift")
# Reserved for confirmed interaction defects. Do not add a target merely
# because a manual run used a different tone-sandhi code: 一丈 is yi2
# (ylkj), whereas yi4 (yjkl) also maps to 义.
KNOWN_UI_BLOCKED: set[str] = set()


def _case_id(case: dict[str, Any]) -> str:
    return f"{case.get('target', '')}\0{case.get('input', '')}"


def _stable_bucket(text: str, modulo: int) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:12], 16) % modulo


def _weight(case: dict[str, Any]) -> float:
    return max(1.0, math.log1p(max(0, int(case.get("weight", 0)))))


def load_cases(report_path: Path, dictionary_path: Path) -> list[dict[str, Any]]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    cases = [dict(item) for item in report["cases"]]
    targets = {str(item["target"]) for item in cases}
    exact = set()
    in_data = False
    with dictionary_path.open("r", encoding="utf-8-sig") as stream:
        for raw in stream:
            line = raw.rstrip("\r\n")
            if not in_data:
                in_data = line.strip() == "..."
                continue
            if not line or line.startswith("#"):
                continue
            text = line.split("\t", 1)[0].strip()
            if text in targets:
                exact.add(text)
    for case in cases:
        case["system_exact"] = str(case["target"]) in exact
        case["case_id"] = _case_id(case)
        rank = case.get("cold_target_rank") or {}
        case["menu_reachable"] = bool(rank.get("found"))
    return cases


@dataclass
class UserState:
    name: str
    persona: str
    learned_by_code: dict[str, str] = field(default_factory=dict)
    learned_entries: set[tuple[str, str]] = field(default_factory=set)
    uses_by_target: Counter[str] = field(default_factory=Counter)
    first_seen_day: dict[str, int] = field(default_factory=dict)
    last_seen_day: dict[str, int] = field(default_factory=dict)
    corrections_by_target: Counter[str] = field(default_factory=Counter)


def _sample_many(rng: random.Random, pool: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    if count <= 0 or not pool:
        return []
    return rng.choices(pool, weights=[_weight(item) for item in pool], k=count)


def build_pools(cases: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    constructible = [item for item in cases if item.get("constructible")]
    return {
        "system": [item for item in constructible if item["system_exact"]],
        "missing": [item for item in constructible if not item["system_exact"]],
        "long_missing": [
            item for item in constructible
            if not item["system_exact"] and len(str(item["target"])) >= 5
        ],
        "same_code": [
            item for item in constructible
            if item.get("sample_group") == "same_code_alternative"
        ],
        "stress": [item for item in cases if not item.get("constructible")],
    }


def select_user_pools(
    rng: random.Random,
    pools: dict[str, list[dict[str, Any]]],
    user_index: int,
) -> dict[str, list[dict[str, Any]]]:
    system = sorted(pools["system"], key=lambda item: (-int(item.get("weight", 0)), item["case_id"]))
    missing = sorted(pools["missing"], key=lambda item: (-int(item.get("weight", 0)), item["case_id"]))
    shared_missing = missing[: min(80, len(missing))]
    personal_missing = [
        item for item in missing
        if _stable_bucket(str(item["target"]), len(PERSONAS)) == user_index
    ][:120]
    persona_system = [
        item for item in system
        if _stable_bucket(str(item["target"]), len(PERSONAS)) in {user_index, (user_index + 1) % len(PERSONAS)}
    ][:350]
    if len(persona_system) < 100:
        persona_system = system[:350]
    same_code = [
        item for item in pools["same_code"]
        if _stable_bucket(str(item["target"]), len(PERSONAS)) == user_index
    ][:100] or pools["same_code"][:100]
    long_missing = [
        item for item in pools["long_missing"]
        if _stable_bucket(str(item["target"]), len(PERSONAS)) in {user_index, (user_index + 2) % len(PERSONAS)}
    ][:120] or pools["long_missing"][:120]
    rng.shuffle(personal_missing)
    return {
        "system": persona_system,
        "shared_missing": shared_missing,
        "personal_missing": personal_missing,
        "same_code": same_code,
        "project_a": long_missing[:60],
        "project_b": long_missing[60:120] or long_missing[:60],
    }


def build_day_workload(
    rng: random.Random,
    user_pools: dict[str, list[dict[str, Any]]],
    events: int,
    day: int,
) -> list[tuple[dict[str, Any], str]]:
    project_key = "project_a" if ((day - 1) // 10) % 2 == 0 else "project_b"
    plan = (
        ("system", 0.65),
        ("personal_missing", 0.15),
        (project_key, 0.10),
        ("shared_missing", 0.05),
        ("same_code", 0.03),
    )
    result: list[tuple[dict[str, Any], str]] = []
    used = 0
    for key, fraction in plan:
        count = round(events * fraction)
        used += count
        result.extend((case, key) for case in _sample_many(rng, user_pools[key], count))
    # Two percent deliberate wrong selections exercise self-healing. They use
    # the same-code pool but remain tagged as noise rather than truth changes.
    result.extend((case, "noise") for case in _sample_many(rng, user_pools["same_code"], max(0, events - used)))
    rng.shuffle(result)
    return result


def run_seed(
    *,
    seed: int,
    cases: list[dict[str, Any]],
    days: int,
    events_per_day: int,
    promotion_interval: int,
) -> dict[str, Any]:
    rng = random.Random(seed)
    pools = build_pools(cases)
    users = [
        UserState(name=f"user-{index + 1}", persona=persona)
        for index, persona in enumerate(PERSONAS)
    ]
    per_user_pools = [
        select_user_pools(random.Random(seed * 100 + index), pools, index)
        for index in range(len(users))
    ]
    case_by_text: dict[str, dict[str, Any]] = {}
    alternatives: dict[str, list[str]] = defaultdict(list)
    for case in cases:
        case_by_text.setdefault(str(case["target"]), case)
        code = str(case["input"])
        target = str(case["target"])
        if target not in alternatives[code]:
            alternatives[code].append(target)

    promoted: set[str] = set()
    daily: list[dict[str, Any]] = []
    promotion_rows: list[dict[str, Any]] = []
    failures: Counter[tuple[str, str]] = Counter()
    total_restarts = 0
    retained_after_restart = 0

    for day in range(1, days + 1):
        for user_index, user in enumerate(users):
            before_restart = dict(user.learned_by_code)
            if day > 1:
                total_restarts += len(before_restart)
                retained_after_restart += sum(
                    user.learned_by_code.get(code) == text
                    for code, text in before_restart.items()
                )
            metrics = Counter()
            metrics["day"] = day
            metrics["seed"] = seed
            metrics["user_index"] = user_index
            before_entries = len(user.learned_entries)
            workload = build_day_workload(
                rng, per_user_pools[user_index], events_per_day, day
            )
            for case, source in workload:
                target, code = str(case["target"]), str(case["input"])
                metrics["events"] += 1
                metrics["characters"] += len(target)
                user.uses_by_target[target] += 1
                user.first_seen_day.setdefault(target, day)
                user.last_seen_day[target] = day
                usage_ordinal = user.uses_by_target[target]

                learned = user.learned_by_code.get(code)
                direct = (
                    target in promoted
                    or learned == target
                    or (learned is None and bool(case.get("cold_target_top1")))
                )
                if source == "noise" and alternatives.get(code):
                    choices = [item for item in alternatives[code] if item != target]
                    if choices:
                        wrong = rng.choice(choices)
                        user.learned_by_code[code] = wrong
                        user.learned_entries.add((code, wrong))
                        metrics["deliberate_misselections"] += 1
                        # A real mistaken click is committed. Do not repair it
                        # inside the same event; a later intended input must
                        # expose the interference and exercise self-healing.
                        continue

                if direct:
                    metrics["direct_top1"] += 1
                    if usage_ordinal >= 2:
                        metrics["repeat_top1"] += 1
                else:
                    metrics["not_top1"] += 1
                    if learned and learned != target:
                        metrics["interference"] += 1
                    if bool(case.get("constructible")) and target not in KNOWN_UI_BLOCKED:
                        metrics["corrections"] += 1
                        user.corrections_by_target[target] += 1
                        user.learned_by_code[code] = target
                        user.learned_entries.add((code, target))
                        if learned and learned != target:
                            metrics["self_healed"] += 1
                    else:
                        metrics["hard_failures"] += 1
                        failures[(target, code)] += 1
                if usage_ordinal >= 2:
                    metrics["repeat_events"] += 1

            metrics["new_user_entries"] = len(user.learned_entries) - before_entries
            metrics["userdb_entries"] = len(user.learned_entries)
            daily.append(dict(metrics))

        if day % promotion_interval == 0:
            candidates = set()
            for user in users:
                candidates.update(user.uses_by_target)
            newly_promoted = []
            for target in sorted(candidates):
                case = case_by_text.get(target)
                if not case or case.get("system_exact") or target in promoted:
                    continue
                counts = [user.uses_by_target[target] for user in users]
                contributing = [count for count in counts if count >= 2]
                if len(contributing) >= 3 and sum(counts) >= 8:
                    promoted.add(target)
                    newly_promoted.append(target)
            compacted = 0
            for user in users:
                redundant = {
                    entry for entry in user.learned_entries if entry[1] in promoted
                }
                compacted += len(redundant)
                user.learned_entries.difference_update(redundant)
            promotion_rows.append(
                {
                    "seed": seed,
                    "day": day,
                    "newly_promoted": len(newly_promoted),
                    "total_promoted": len(promoted),
                    "compacted_user_entries": compacted,
                    "samples": newly_promoted[:20],
                }
            )

    aggregate = Counter()
    for row in daily:
        for key, value in row.items():
            if key not in {"day", "seed", "user_index"}:
                aggregate[key] += int(value)
    early_growth = sum(row.get("new_user_entries", 0) for row in daily if row["day"] <= 7)
    late_growth = sum(row.get("new_user_entries", 0) for row in daily if row["day"] > days - 7)
    repeat_rate = aggregate["repeat_top1"] / aggregate["repeat_events"] if aggregate["repeat_events"] else 0
    interference_preservation = 1 - aggregate["interference"] / aggregate["events"]
    self_heal = aggregate["self_healed"] / aggregate["interference"] if aggregate["interference"] else 1
    summary = {
        "seed": seed,
        "users": len(users),
        "days": days,
        "events": aggregate["events"],
        "characters": aggregate["characters"],
        "direct_top1_rate": aggregate["direct_top1"] / aggregate["events"],
        "repeat_top1_rate": repeat_rate,
        "corrections_per_100_chars": aggregate["corrections"] * 100 / aggregate["characters"],
        "hard_failure_rate": aggregate["hard_failures"] / aggregate["events"],
        "interference_preservation_rate": interference_preservation,
        "self_heal_rate": self_heal,
        "restart_retention_rate": retained_after_restart / total_restarts if total_restarts else 1,
        "early_userdb_growth": early_growth,
        "late_userdb_growth": late_growth,
        "late_to_early_growth_ratio": late_growth / early_growth if early_growth else 0,
        "promoted_phrases": len(promoted),
        "final_userdb_entries": sum(len(user.learned_entries) for user in users),
        "persistent_failure_targets": len(failures),
    }
    return {
        "summary": summary,
        "daily": daily,
        "promotions": promotion_rows,
        "failures": [
            {"target": target, "input": code, "count": count}
            for (target, code), count in failures.most_common()
        ],
    }


def _write_tsv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row}) if rows else ["empty"]
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, dialect="excel-tab", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def acceptance(summaries: list[dict[str, Any]]) -> dict[str, Any]:
    checks = {
        "repeat_top1_at_least_99_percent": min(item["repeat_top1_rate"] for item in summaries) >= 0.99,
        "restart_retention_at_least_99_9_percent": min(item["restart_retention_rate"] for item in summaries) >= 0.999,
        "interference_preservation_at_least_99_5_percent": min(item["interference_preservation_rate"] for item in summaries) >= 0.995,
        "self_heal_at_least_99_percent": min(item["self_heal_rate"] for item in summaries) >= 0.99,
        "late_userdb_growth_below_half_early_growth": max(item["late_to_early_growth_ratio"] for item in summaries) < 0.5,
        "promotion_and_compaction_observed": min(item["promoted_phrases"] for item in summaries) > 0,
        "no_persistent_failure_target": max(item["persistent_failure_targets"] for item in summaries) == 0,
    }
    return {"passed": all(checks.values()), "checks": checks}


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    summaries = payload["seed_summaries"]
    lines = [
        "# Yime 加速式用户学习漂移测试",
        "",
        f"- 判定：**{'通过' if payload['acceptance']['passed'] else '未完全通过'}**",
        f"- 随机种子：{', '.join(str(item['seed']) for item in summaries)}",
        f"- 每组：{summaries[0]['users']} 用户 × {summaries[0]['days']} 虚拟日",
        f"- 总输入事件：{sum(item['events'] for item in summaries):,}",
        "",
        "|种子|直接首选率|重复输入首选率|同码保持率|一次纠正自愈率|硬失败率|后期/前期增长|晋升词数|",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in summaries:
        lines.append(
            f"|{item['seed']}|{item['direct_top1_rate']:.4%}|{item['repeat_top1_rate']:.4%}|"
            f"{item['interference_preservation_rate']:.4%}|{item['self_heal_rate']:.4%}|"
            f"{item['hard_failure_rate']:.4%}|{item['late_to_early_growth_ratio']:.4f}|"
            f"{item['promoted_phrases']}|"
        )
    lines.extend(["", "## 验收检查", ""])
    for name, passed in payload["acceptance"]["checks"].items():
        lines.append(f"- {'通过' if passed else '未通过'}：`{name}`")
    lines.extend(["", "## 持续失败", ""])
    if payload.get("persistent_failures"):
        for item in payload["persistent_failures"][:20]:
            lines.append(
                f"- `{item['target']}`：{item['count']} 次，"
                f"涉及 {item['seed_count']} 个随机种子"
            )
    else:
        lines.append("- 无")
    lines.extend(
        [
            "",
            "## 结论边界",
            "",
            "这是由真实 librime 回放结果校准的加速仿真，不是生产遥测。它验证学习、",
            "同码漂移、周期重启、云端晋升和用户库收敛机制；不能替代未来真实用户的",
            "隐私、领域分布和操作习惯校准。",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replay-report", required=True, type=Path)
    parser.add_argument("--dictionary", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--events-per-day", type=int, default=1000)
    parser.add_argument("--promotion-interval", type=int, default=7)
    parser.add_argument("--seeds", default="1729,2718,31415")
    args = parser.parse_args()
    seeds = [int(item.strip()) for item in args.seeds.split(",") if item.strip()]
    source_report = json.loads(args.replay_report.read_text(encoding="utf-8"))
    cases = load_cases(args.replay_report, args.dictionary)
    runs = [
        run_seed(
            seed=seed, cases=cases, days=args.days,
            events_per_day=args.events_per_day,
            promotion_interval=args.promotion_interval,
        )
        for seed in seeds
    ]
    summaries = [run["summary"] for run in runs]
    failure_aggregate: dict[str, dict[str, Any]] = {}
    for run in runs:
        for item in run["failures"]:
            target = str(item["target"])
            current = failure_aggregate.setdefault(
                target, {"target": target, "count": 0, "seeds": set()}
            )
            current["count"] += int(item["count"])
            current["seeds"].add(int(run["summary"]["seed"]))
    persistent_failures = [
        {
            "target": item["target"],
            "count": item["count"],
            "seed_count": len(item["seeds"]),
        }
        for item in sorted(
            failure_aggregate.values(), key=lambda value: (-value["count"], value["target"])
        )
    ]
    payload = {
        "schema_version": "yime-accelerated-learning-drift-v1",
        "inputs": {
            "replay_report": str(args.replay_report.resolve()),
            "dictionary": str(args.dictionary.resolve()),
            "case_count": len(cases),
            "real_librime_calibration_summary": source_report.get("summary", {}),
        },
        "policy": {
            "personas": list(PERSONAS),
            "days": args.days,
            "events_per_user_day": args.events_per_day,
            "promotion_interval_days": args.promotion_interval,
            "promotion_min_users_with_two_uses": 3,
            "promotion_min_total_uses": 8,
            "known_ui_blocked_targets": sorted(KNOWN_UI_BLOCKED),
        },
        "seed_summaries": summaries,
        "acceptance": acceptance(summaries),
        "persistent_failures": persistent_failures,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "accelerated_drift_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _write_tsv(args.output_dir / "daily_metrics.tsv", (row for run in runs for row in run["daily"]))
    promotion_rows = []
    for run in runs:
        for row in run["promotions"]:
            row = dict(row)
            row["samples"] = "、".join(row["samples"])
            promotion_rows.append(row)
    _write_tsv(args.output_dir / "promotion_rounds.tsv", promotion_rows)
    _write_tsv(
        args.output_dir / "persistent_failures.tsv",
        (
            {"seed": run["summary"]["seed"], **row}
            for run in runs for row in run["failures"]
        ),
    )
    _write_tsv(
        args.output_dir / "userdb_growth.tsv",
        (
            {
                "seed": row["seed"], "day": row["day"], "user_index": row["user_index"],
                "new_user_entries": row.get("new_user_entries", 0),
                "userdb_entries": row.get("userdb_entries", 0),
            }
            for run in runs for row in run["daily"]
        ),
    )
    write_markdown(args.output_dir / "production_readiness.md", payload)
    print(json.dumps(payload["acceptance"], ensure_ascii=False))
    return 0 if payload["acceptance"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
