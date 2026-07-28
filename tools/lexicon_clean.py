#!/usr/bin/env python3
"""Compatibility entry point for the retired lexicon-cleanup workflow.

Candidate inventory is now evaluated as R0-R5 dynamic coverage.  The legacy
filename remains only so old local commands reach the canonical read-only
report instead of reviving deletion-oriented behavior.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.evaluate_dynamic_candidate_coverage import main  # noqa: E402


if __name__ == "__main__":
    print(
        "tools/lexicon_clean.py 已退役；转交 "
        "tools/evaluate_dynamic_candidate_coverage.py。",
        file=sys.stderr,
    )
    raise SystemExit(main())
