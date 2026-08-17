"""Materialize explicit, non-productive erhua annotations and code routes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from yime.connected_speech.erhua_lexicon import write_explicit_erhua_bundles


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build explicit word-final erhua annotations and dual-route aliases."
    )
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--annotations", type=Path)
    parser.add_argument("--aliases", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    annotations, aliases, counts = write_explicit_erhua_bundles(
        repo_root=args.repo_root,
        annotations_path=args.annotations,
        aliases_path=args.aliases,
    )
    print(
        json.dumps(
            {"annotations": str(annotations), "aliases": str(aliases), "counts": counts},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
