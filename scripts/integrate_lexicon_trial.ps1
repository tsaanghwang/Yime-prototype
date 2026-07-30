# Compatibility entry point for the retired trial workflow.
# It now invokes only the unified source_lexicon.sqlite3 production chain.
param(
    [switch]$SkipBuild,
    [switch]$ApplyRuntime,
    [switch]$SkipLexiconTests,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path $PSScriptRoot -Parent
Set-Location $RepoRoot

function Resolve-Python {
    if (Test-Path "venv312/Scripts/python.exe") { return "venv312/Scripts/python.exe" }
    if (Test-Path ".venv/Scripts/python.exe") { return ".venv/Scripts/python.exe" }
    return "python"
}

function Invoke-CommandArray([object[]]$Command) {
    Write-Host ("+ " + ($Command -join " ")) -ForegroundColor Cyan
    if ($DryRun) { return }
    & $Command[0] $Command[1..($Command.Count - 1)]
    if ($LASTEXITCODE -ne 0) {
        throw "command failed with exit code $LASTEXITCODE"
    }
}

$Python = Resolve-Python
$Rebuild = @($Python, "internal_data/pinyin_source_db/rebuild_pinyin_assets.py")
if ($SkipBuild) { $Rebuild += "--skip-bundle-build" }

Write-Host "Legacy source_pinyin.db trial chain is retired; using unified source." -ForegroundColor Yellow
Invoke-CommandArray $Rebuild

if ($ApplyRuntime) {
    Invoke-CommandArray @($Python, "-m", "yime.import_danzi_into_prototype_tables")
    Invoke-CommandArray @($Python, "-m", "yime.import_duozi_into_prototype_tables")
    Invoke-CommandArray @($Python, "-m", "yime.refresh_runtime_yime_codes", "--apply")
}

if (-not $SkipLexiconTests) {
    Invoke-CommandArray @("cmd", "/c", "scripts/run_tests.cmd")
}
