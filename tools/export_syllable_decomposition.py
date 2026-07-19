"""Export the exhaustive syllable decomposition table used by the Windows inspector."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from yime.utils.syllable_decomposition_audit import (  # noqa: E402
    DEFAULT_INVENTORY_PATH,
    DEFAULT_OUTPUT_PATH,
    export_syllable_decomposition_tsv,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export all canonical Pinyin decomposition stages.")
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()
    count = export_syllable_decomposition_tsv(args.output, inventory_path=args.inventory)
    print(f"Exported {count} syllable decomposition rows to {args.output}")


if __name__ == "__main__":
    main()

