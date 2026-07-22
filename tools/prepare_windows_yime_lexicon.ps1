param(
    [string]$OutputDir = "",
    [string]$WindowsYimeRoot = "C:\dev\Yime",
    [switch]$SkipWindowsDerivation
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $repoRoot "venv312\Scripts\python.exe"
$runtimeDb = Join-Path $repoRoot "yime\pinyin_hanzi.db"
$exporter = Join-Path $repoRoot "yime\export_rime_yime.py"
$auxiliaryExporter = Join-Path $repoRoot "tools\prepare_windows_yime_auxiliary_assets.py"

if (-not $OutputDir) {
    $OutputDir = Join-Path $repoRoot ".generated\windows_yime_import"
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$resolvedOutputDir = (Resolve-Path -LiteralPath $OutputDir).Path

foreach ($requiredPath in @($python, $runtimeDb, $exporter, $auxiliaryExporter)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "Required prototype asset is missing: $requiredPath"
    }
}

$fullDictionary = Join-Path $resolvedOutputDir "yime_full.dict.yaml"
$pinyinCodes = Join-Path $resolvedOutputDir "yime_pinyin_codes.tsv"

& $python $exporter `
    --db $runtimeDb `
    --output-dir $resolvedOutputDir `
    --mode full `
    --code-form layout-key `
    --schema-id yime_full `
    --schema-name "Yime等长" `
    --pinyin-codes-output $pinyinCodes
if ($LASTEXITCODE -ne 0) {
    throw "Prototype full-lexicon export failed with exit code $LASTEXITCODE"
}

& $python $auxiliaryExporter --output-dir $resolvedOutputDir
if ($LASTEXITCODE -ne 0) {
    throw "Prototype auxiliary-asset export failed with exit code $LASTEXITCODE"
}

if (-not $SkipWindowsDerivation) {
    $importer = Join-Path $WindowsYimeRoot "tools\import-yime-full-lexicon.ps1"
    if (-not (Test-Path -LiteralPath $importer)) {
        throw "Windows Yime importer is missing: $importer"
    }

    $derivedOutput = Join-Path $resolvedOutputDir "windows_derived"
    $previousGoCache = $env:GOCACHE
    $env:GOCACHE = Join-Path $resolvedOutputDir ".go-cache"
    New-Item -ItemType Directory -Force -Path $env:GOCACHE | Out-Null
    try {
        powershell.exe -NoProfile -ExecutionPolicy Bypass -File $importer `
            -InputPath $fullDictionary `
            -OutputDir $derivedOutput
        if ($LASTEXITCODE -ne 0) {
            throw "Windows Yime derivation failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        if ($null -eq $previousGoCache) {
            Remove-Item Env:GOCACHE -ErrorAction SilentlyContinue
        }
        else {
            $env:GOCACHE = $previousGoCache
        }
    }

    foreach ($name in @(
        "yime_full.dict.yaml",
        "yime_variable.dict.yaml",
        "yime_shorthand.dict.yaml",
        "yime_lexicon_manifest.json"
    )) {
        $derivedPath = Join-Path $derivedOutput $name
        if (-not (Test-Path -LiteralPath $derivedPath)) {
            throw "Windows Yime derivation did not produce: $derivedPath"
        }
    }
}

Write-Host "Windows Yime lexicon handoff is ready: $resolvedOutputDir"
Write-Host "This command prepares files only; it does not deploy them to PIME/Rime."
