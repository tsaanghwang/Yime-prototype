"""Shared rejection message for product workflows retired from this repository."""

from __future__ import annotations

import sys


PRODUCT_REPOSITORY = r"C:\dev\Yime"
BOUNDARY_DOCUMENT = "docs/DETACHED_MAINTENANCE_BOUNDARY.md"


def obsolete_workflow_message(workflow: str) -> str:
    return (
        f"Obsolete workflow blocked in the detached maintenance repository: {workflow}. "
        f"Run product build, packaging, release, and Windows Yime integration work in "
        f"{PRODUCT_REPOSITORY}. See {BOUNDARY_DOCUMENT}."
    )


def reject_obsolete_workflow(workflow: str) -> int:
    print(obsolete_workflow_message(workflow), file=sys.stderr)
    return 2

