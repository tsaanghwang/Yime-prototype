"""Compatibility shim for canonical mapping helpers."""

from yime.utils.canonical_yime_mapping import (
    CANONICAL_PATCH_PATH,
    WORKSPACE_ROOT,
    build_bmp_to_canonical_map,
    build_canonical_mapping_rows,
    build_canonical_pinyin_rows,
    canonicalize_code,
    convert_legacy_code_to_primary,
    load_canonical_code_map,
    load_canonical_patch_map,
    load_primary_code_map,
    load_json,
    sync_canonical_mapping_table,
)

__all__ = [
    "CANONICAL_PATCH_PATH",
    "WORKSPACE_ROOT",
    "build_bmp_to_canonical_map",
    "build_canonical_mapping_rows",
    "build_canonical_pinyin_rows",
    "canonicalize_code",
    "convert_legacy_code_to_primary",
    "load_canonical_code_map",
    "load_canonical_patch_map",
    "load_primary_code_map",
    "load_json",
    "sync_canonical_mapping_table",
]
