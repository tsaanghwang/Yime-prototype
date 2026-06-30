"""Compatibility shim for the Yime-to-Rime exporter."""

if __name__ == "__main__" and __package__ is None:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from yime.utils.rime_export import (
    DEFAULT_DB_PATH,
    DEFAULT_OUTPUT_DIR,
    RimeExportPaths,
    RimeExportResult,
    export_rime_files,
    main,
)


__all__ = [
    "DEFAULT_DB_PATH",
    "DEFAULT_OUTPUT_DIR",
    "RimeExportPaths",
    "RimeExportResult",
    "export_rime_files",
    "main",
]


if __name__ == "__main__":
    main()
