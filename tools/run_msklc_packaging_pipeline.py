from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.detached_maintenance_boundary import reject_obsolete_workflow


def main() -> int:
    return reject_obsolete_workflow("MSKLC product packaging")


if __name__ == "__main__":
    raise SystemExit(main())
