"""Validate the structured zaoyin source and optionally write a proposal.

This command never overwrites the live stable registry.  ``--write-proposal``
is deliberately limited to the repository's ``.generated`` directory.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from syllable.analysis.zaoyin_pianyin_source import (  # noqa: E402
    audit_zaoyin_pianyin_source,
    build_proposed_registry,
)


DEFAULT_PROPOSAL = (
    PROJECT_ROOT
    / ".generated"
    / "zaoyin-registry"
    / "zaoyin_yinyuan_enhanced.proposed.json"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-proposal",
        action="store_true",
        help="Write the 27-entry proposal under .generated; never updates the live registry.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_PROPOSAL)
    args = parser.parse_args()

    audit = audit_zaoyin_pianyin_source()
    print(json.dumps(audit.as_dict(), ensure_ascii=False, indent=2))
    if not audit.passed:
        return 1

    if args.write_proposal:
        output = args.output.resolve()
        generated_root = (PROJECT_ROOT / ".generated").resolve()
        if generated_root not in output.parents:
            raise SystemExit("--output 必须位于仓库 .generated 目录内")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(build_proposed_registry(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"proposal: {output}")
    else:
        print("check only; live registry unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
