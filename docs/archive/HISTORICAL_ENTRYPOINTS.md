# Historical entrypoints and documents

This index separates the detached maintenance workflow from retained compatibility and historical material. The machine-readable source is `internal_data/archived_entrypoints.json`.

Files are archived in place. Moving or deleting them would break unknown consumers and existing gates; the archive catalog instead records their state and current replacement.

## Current boundaries

- `tools/lexicon_clean.py` is a retired diagnostic. Use `tools/evaluate_dynamic_candidate_coverage.py` for the current coverage gate.
- The two `drop_legacy_*` tools are maintenance-only migration helpers, not rebuild steps.
- The old `yime/import_*`, runtime refresh, and JSON export scripts are compatibility paths. New work starts from the unified source bundle and the two-level runtime trial.
- Portable, Setup, friend-trial, MSKLC, frontend-deployment, seed-install, and Windows handoff entrypoints are blocked. They only direct product work to `C:\dev\Yime`.
- `docs/windows-klc-workflow.md` and `docs/MSKLC_RELEASE_QUICKSTART.md` are historical workflow notes; use `docs/DETACHED_MAINTENANCE_BOUNDARY.md` for the current boundary.
- `docs/project/WIKI_SPEECH_TRAJECTORY_REVISION_DRAFT.md` remains a suspended theory draft and does not define the implemented architecture.

## Maintenance rule

Any new one-click prototype gate must validate the archive catalog but exclude every entry whose `prototype_acceptance` value is false. Restoring one of these paths to an executable product workflow is not a maintenance action in this repository. Product work belongs in `C:\dev\Yime`; any exceptional recovery export requires explicit authorization and an independent, content-hashed archive.
