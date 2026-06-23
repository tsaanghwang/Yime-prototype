import json
from pathlib import Path
from typing import Any, Mapping, TypedDict, cast

# cspell:ignore combinability

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / "internal_data" / "shouyin_ganyin_combinability.json"
DEFAULT_OUTPUT = ROOT / "internal_data" / "shouyin_direct_following_constraints.json"


class SummaryRow(TypedDict):
    noise: str
    choice_count: int
    top_choices: list[str]


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data: Any = json.load(handle)
    return cast(dict[str, Any], data) if isinstance(data, dict) else {}


def sort_symbol_keys(values: list[str]) -> list[str]:
    def sort_key(item: str) -> tuple[str, int]:
        return item[0], int(item[1:])

    return sorted(values, key=sort_key)


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    items = cast(list[Any], value)
    return [item for item in items if isinstance(item, str)]


def _as_str_int_dict(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, int] = {}
    for key, val in cast(Mapping[Any, Any], value).items():
        if isinstance(key, str) and isinstance(val, int):
            result[key] = val
    return result


def build_constraints(combinability_data: Mapping[str, Any]) -> dict[str, Any]:
    by_noise_raw = combinability_data.get("by_noise", {})
    by_noise: dict[str, Any] = cast(dict[str, Any], by_noise_raw) if isinstance(by_noise_raw, dict) else {}

    summary_rows: list[SummaryRow] = []
    output: dict[str, Any] = {
        "metadata": {
            "source": "internal_data/shouyin_ganyin_combinability.json",
            "description": "Compact direct-following constraints for keyboard layout design. Each Nxx lists the Mxx values that can appear immediately after it in encoded syllables.",
        },
        "summary": {
            "noise_symbol_count": len(by_noise),
            "constraint_edges": 0,
        },
        "by_noise": {},
        "ranked_noise_by_choice_count": [],
    }

    edge_count = 0
    for noise_key in sort_symbol_keys(list(by_noise.keys())):
        entry_raw = by_noise.get(noise_key, {})
        entry: dict[str, Any] = cast(dict[str, Any], entry_raw) if isinstance(entry_raw, dict) else {}

        direct_following = _as_str_list(entry.get("direct_following_musicals", []))
        direct_counts = _as_str_int_dict(entry.get("direct_following_counts", {}))
        edge_count += len(direct_following)

        sorted_choices = sorted(
            direct_following,
            key=lambda musical_key: (-direct_counts.get(musical_key, 0), musical_key),
        )

        output["by_noise"][noise_key] = {
            "choice_count": len(direct_following),
            "choices": direct_following,
            "choices_ranked_by_frequency": sorted_choices,
            "choice_counts": {musical_key: direct_counts.get(musical_key, 0) for musical_key in sorted_choices},
            "example_syllables": _as_str_list(entry.get("example_syllables", []))[:8],
        }

        summary_rows.append(
            {
                "noise": noise_key,
                "choice_count": len(direct_following),
                "top_choices": sorted_choices[:6],
            }
        )

    output["summary"]["constraint_edges"] = edge_count
    output["ranked_noise_by_choice_count"] = sorted(
        summary_rows,
        key=lambda row: (row["choice_count"], row["noise"]),
    )
    return output


def main() -> None:
    combinability_data = load_json(DEFAULT_INPUT)
    output = build_constraints(combinability_data)

    with DEFAULT_OUTPUT.open("w", encoding="utf-8") as handle:
        json.dump(output, handle, ensure_ascii=False, indent=2)

    print(f"Direct-following constraints written to {DEFAULT_OUTPUT}")


if __name__ == "__main__":
    main()
