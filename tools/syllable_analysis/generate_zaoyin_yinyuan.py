"""Compatibility wrapper for the safe structured-zaoyin registry command.

The historical script overwrote the live enhanced registry.  The replacement
performs validation by default and only writes a proposal below ``.generated``
when ``--write-proposal`` is explicitly supplied.
"""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.rebuild_zaoyin_registry import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
