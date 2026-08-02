# Historical entrypoints and documents

This index separates the current prototype workflow from retained compatibility and historical material. The machine-readable source is `internal_data/archived_entrypoints.json`.

Files are archived in place. Moving or deleting them would break unknown consumers and existing gates; the archive catalog instead records their state and current replacement.

## Current boundaries

- `tools/lexicon_clean.py` is a retired diagnostic. Use `tools/evaluate_dynamic_candidate_coverage.py` for the current coverage gate.
- The two `drop_legacy_*` tools are maintenance-only migration helpers, not rebuild steps.
- The old `yime/import_*`, runtime refresh, and JSON export scripts are compatibility paths. New work starts from the unified source bundle and the two-level runtime trial.
- `prepare_windows_yime_*` and `verify_default_runtime_handoff.py` belong to external Windows handoff. Prototype acceptance must never call them implicitly.
- `docs/windows-klc-workflow.md` is a historical workflow note; use `docs/MSKLC_RELEASE_QUICKSTART.md` for the current entrypoint.
- `docs/project/WIKI_SPEECH_TRAJECTORY_REVISION_DRAFT.md` remains a suspended theory draft and does not define the implemented architecture.

## Maintenance rule

Any new one-click prototype gate must validate the archive catalog but exclude every entry whose `prototype_acceptance` value is false. Restoring one of these paths to the main workflow requires an explicit catalog and documentation change.