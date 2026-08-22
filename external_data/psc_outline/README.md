# PSC evidence bundle

This directory is the in-repository home of the PSC evidence formerly kept in
a sibling workspace. It supports historical source auditing, provenance review,
and recovery research only; it is not a Yime product input or release handoff.

The local-only `psc_outline_ocr.sqlite3` database is the direct dependency of
the repository's PSC audit tools. Its `documents` and `pages` tables refer to
the source PDF/DOC files and OCR page images stored beside it. Those paths are
kept relative to this directory so the evidence bundle remains relocatable.

Large source documents, OCR pages, and SQLite snapshots are intentionally
ignored by Git. Recovery scripts, tests, launchers, and this explanation remain
trackable. The `psc_outline_ocr.before_reparse.sqlite3` file is retained as the
pre-reparse recovery snapshot, and `.merkle-snapshot.pre-migration.json` records
the earlier recovery-tool snapshot. SQLite `-shm` and `-wal` sidecars and
editor/index caches were not migrated.

The pre-reparse database records an earlier rare-word workbook and
passage-pronunciation text export that were already absent from the former
workspace. These are preserved as missing historical references in the recovery
snapshot; no replacement files were fabricated.
