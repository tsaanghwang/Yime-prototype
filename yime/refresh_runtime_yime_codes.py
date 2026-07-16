"""Compatibility shim for the runtime refresh pipeline.

The real implementation now lives in yime.utils.runtime_codes_refresh.
"""

from typing import Any

if __name__ == "__main__" and __package__ is None:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from yime.utils import runtime_codes_refresh as _impl

main = _impl.main


def __getattr__(name: str) -> Any:
    return getattr(_impl, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_impl)))


__all__ = getattr(_impl, "__all__", ())  # pyright: ignore[reportUnsupportedDunderAll]


if __name__ == "__main__":
    raise SystemExit(main())
