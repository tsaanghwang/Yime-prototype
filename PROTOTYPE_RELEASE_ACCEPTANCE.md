# Detached prototype maintenance acceptance

Use the isolated one-click gate after a clean checkout or before accepting a maintenance change in this repository:

```powershell
.\venv312\Scripts\python.exe tools\run_prototype_release_acceptance.py
```

The default run rebuilds the source bundle, input model, recursive composition evidence, static capacity proposal, and two-level trial into a timestamped directory under `.generated/prototype_release_acceptance/`. The trial always uses `--skip-runtime-database`.

It then rebuilds the second-batch, ranking, and dynamic-coverage reports; compares stable statistics with the canonical manifests; checks documentation anchors; verifies syllable audit exports byte-for-byte; runs the layout lock, six headless interaction smoke scenarios, `git diff --check`, and the default pytest gate.

For a quick code-only check against existing canonical artifacts, use `--skip-full-data`. Use `--require-clean` in CI or delivery automation when any tracked or untracked worktree change must fail the run.

Every run writes `acceptance_manifest.json` plus per-step logs. A failed step leaves its evidence in place and returns a non-zero exit code.

This is a local research/recovery gate, not a product release gate. Safety boundaries are strict: the runner never restarts Windows, never invokes an installer, never writes a real user directory, never exports to Windows Yime, and never calls the external handoff scripts listed in `internal_data/prototype_release_acceptance_policy.json`. Product build and release work belongs in `C:\dev\Yime`.
Canonical entrypoint: `tools/run_prototype_release_acceptance.py`.

If a full run is interrupted after the large source, input, recursive, and capacity steps, continue without rebuilding them:

```powershell
.\venv312\Scripts\python.exe tools\run_prototype_release_acceptance.py --reuse-rebuild-from <previous-run-directory>
```

The resumed run still rebuilds the two-level trial and all downstream reports, then performs every drift, smoke, and pytest gate.
Stable rebuild statistics live in `internal_data/prototype_release_baseline.json` so a clean checkout does not depend on pre-existing `.generated` artifacts.

The full and resumed paths also run `tools/refresh_materialized_syllable_inventory.py` immediately after the source bundle so the existing pinyin and Yinjie gates work on a clean checkout.
