# 词库 trial 接入：只换词库层 + 运行时层，不动编码层。
#
# 设计依据（仓库内已有文档/脚本，本文件是对它们的封装）：
#   - docs/project/PINYIN_DATA_MIGRATION.md     运行时链顺序
#   - internal_data/pinyin_source_db/README.md  phase-1 rebuild (default skips codebook)
#   - internal_data/pinyin_source_db/PATCH_POLICY.md  refresh 报错后的补丁决策
#   - scripts/run_tests.cmd                     词库/编码 unittest 门禁（不含 IME）
#   - tools/update_phrase_lexicon_from_large_pinyin.py  同类 orchestrator（外部源版）
#   - scripts/restore_full_pipeline.ps1 -Mode forward  简化版 forward（无报告/备份）
#
# 用法:
#   .\scripts\integrate_lexicon_trial.ps1                    # 建库 + 校验 + 导出；不动 runtime
#   .\scripts\integrate_lexicon_trial.ps1 -ApplyRuntime      # 上述 + prototype/refresh/export
#   .\scripts\integrate_lexicon_trial.ps1 -SkipBuild         # 已有 trial.db，只做 3-4
#   .\scripts\integrate_lexicon_trial.ps1 -DryRun            # 只打印将执行的步骤
#
param(
    [string]$TrialDb = ".generated/source_pinyin.db",
    [string]$CharSource = "",
    [string]$PhraseSource = "",
    [switch]$SkipBuild,
    [switch]$ApplyRuntime,
    [switch]$SkipLexiconTests,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path $PSScriptRoot -Parent
Set-Location $RepoRoot

$GeneratedDir = ".generated"
$RuntimeDb = "yime/pinyin_hanzi.db"
$RuntimeJson = ".generated/runtime_candidates_by_code_true.json"
$EncodingJson = "syllable/codec/yinjie_code.json"
$ReportJson = ".generated/integrate_lexicon_trial_report.json"
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BaselineBackup = "yime/backup/pinyin_hanzi.lexicon_trial_${Timestamp}.bak"

function Resolve-Python {
    if (Test-Path "venv312/Scripts/python.exe") { return "venv312/Scripts/python.exe" }
    if (Test-Path ".venv/Scripts/python.exe") { return ".venv/Scripts/python.exe" }
    return "python"
}

$Python = Resolve-Python

function Write-Step([string]$Title) {
    Write-Host ""
    Write-Host "=== $Title ===" -ForegroundColor Cyan
}

function Invoke-Step([string]$Title, [scriptblock]$Block) {
    Write-Step $Title
    if ($DryRun) {
        Write-Host "[dry-run] skipped" -ForegroundColor DarkYellow
        return
    }
    & $Block
    if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) {
        throw "$Title failed with exit code $LASTEXITCODE"
    }
}

function Invoke-Python([string[]]$Arguments) {
    $quoted = ($Arguments | ForEach-Object {
        if ($_ -match '\s') { """$_""" } else { $_ }
    }) -join " "
    Write-Host "$Python $quoted"
    & $Python @Arguments
}

function Write-Metrics(
    [string]$SourceDbPath,
    [string]$RuntimeDbPath = "",
    [string]$BaselineRuntimeDbPath = "",
    [string]$RuntimeJsonPath = "",
    [string]$EncodingJsonPath = $EncodingJson
) {
    $args = @(
        "tools/lexicon_integration_metrics.py",
        "--source-db", $SourceDbPath,
        "--output", $ReportJson,
        "--encoding-json", $EncodingJsonPath
    )
    if ($RuntimeDbPath) { $args += @("--runtime-db", $RuntimeDbPath) }
    if ($BaselineRuntimeDbPath) { $args += @("--baseline-runtime-db", $BaselineRuntimeDbPath) }
    if ($RuntimeJsonPath) { $args += @("--runtime-json", $RuntimeJsonPath) }
    Invoke-Python $args | Out-Null
}

function Print-ReportSummary {
    if (-not (Test-Path $ReportJson)) {
        Write-Host "Report not found: $ReportJson" -ForegroundColor Yellow
        return
    }
    $report = Get-Content $ReportJson -Raw -Encoding UTF8 | ConvertFrom-Json

    Write-Host ""
    Write-Host "=== integrate_lexicon_trial report ===" -ForegroundColor Green
    Write-Host "report: $ReportJson"

    $src = $report.source_db
    Write-Host ("source_db: {0} ({1} bytes)" -f $src.path, $src.bytes)
    if ($src.counts.char_readings) {
        Write-Host ("  char_readings:   {0}" -f $src.counts.char_readings)
    }
    if ($src.counts.phrase_readings) {
        Write-Host ("  phrase_readings: {0}" -f $src.counts.phrase_readings)
    }
    Write-Host ("  sha256: {0}" -f $src.sha256)

    if ($report.PSObject.Properties.Name -contains "baseline_runtime_db") {
        $base = $report.baseline_runtime_db
        Write-Host ("baseline_runtime_db: {0}" -f $base.path)
        if ($base.counts.single_char_readings) {
            Write-Host ("  single_char_readings:          {0}" -f $base.counts.single_char_readings)
        }
        if ($base.counts.runtime_candidates_materialized) {
            Write-Host ("  runtime_candidates_materialized: {0}" -f $base.counts.runtime_candidates_materialized)
        }
        Write-Host ("  sha256: {0}" -f $base.sha256)
    }

    if ($report.PSObject.Properties.Name -contains "runtime_db") {
        $rt = $report.runtime_db
        Write-Host ("runtime_db: {0}" -f $rt.path)
        if ($rt.counts.single_char_readings) {
            Write-Host ("  single_char_readings:          {0}" -f $rt.counts.single_char_readings)
        }
        if ($rt.counts.runtime_candidates_materialized) {
            Write-Host ("  runtime_candidates_materialized: {0}" -f $rt.counts.runtime_candidates_materialized)
        }
        Write-Host ("  sha256: {0}" -f $rt.sha256)
    }

    if ($report.PSObject.Properties.Name -contains "runtime_json") {
        $rj = $report.runtime_json
        Write-Host ("runtime_json: {0} ({1} bytes) sha256={2}" -f $rj.path, $rj.bytes, $rj.sha256)
    }

    $enc = $report.encoding_json
    Write-Host ("encoding_json (must stay unchanged): {0}" -f $enc.path)
    Write-Host ("  sha256: {0}" -f $enc.sha256)
}

# --- preflight ---
Write-Step "preflight"
Write-Host "repo: $RepoRoot"
Write-Host "python: $Python"
Write-Host "trial_db: $TrialDb"
Write-Host "apply_runtime: $($ApplyRuntime.IsPresent)"
Write-Host "dry_run: $($DryRun.IsPresent)"

if (-not $DryRun) {
    New-Item -ItemType Directory -Force -Path $GeneratedDir | Out-Null
    New-Item -ItemType Directory -Force -Path "yime/backup" | Out-Null
}

$encodingHashBefore = $null
if ((Test-Path $EncodingJson) -and -not $DryRun) {
    $encodingHashBefore = (Get-FileHash $EncodingJson -Algorithm SHA256).Hash
}

# --- step 2: build + validate trial source db ---
if (-not $SkipBuild) {
    $buildArgs = @(
        "internal_data/pinyin_source_db/build_source_pinyin_db.py",
        "--db", $TrialDb
    )
    if ($CharSource) {
        $buildArgs += @("--char-source", $CharSource)
    }
    if ($PhraseSource) {
        $buildArgs += @("--phrase-source", $PhraseSource)
    }

    Invoke-Step "2/4 build_source_pinyin_db -> $TrialDb" {
        Invoke-Python $buildArgs
    }

    Invoke-Step "2/4 validate_source_pinyin_db" {
        Invoke-Python @(
            "internal_data/pinyin_source_db/validate_source_pinyin_db.py",
            "--db", $TrialDb
        )
    }
} else {
    Write-Step "2/4 build/validate (skipped -SkipBuild)"
    if (-not $DryRun -and -not (Test-Path $TrialDb)) {
        throw "Trial DB not found: $TrialDb"
    }
}

Invoke-Step "metrics after source build" {
    Write-Metrics -SourceDbPath $TrialDb
}

# --- step 3: lexicon export (phase 1; default leaves codebook unchanged) ---
Invoke-Step "3/4 rebuild_pinyin_assets.py (phase 1)" {
    $env:YIME_SOURCE_PINYIN_DB = (Resolve-Path $TrialDb).Path
    try {
        Invoke-Python @(
            "internal_data/pinyin_source_db/rebuild_pinyin_assets.py",
            "--db", $TrialDb
        )
    } finally {
        Remove-Item Env:YIME_SOURCE_PINYIN_DB -ErrorAction SilentlyContinue
    }
}

if (-not $SkipLexiconTests) {
    Invoke-Step "3/4 lexicon gate: run_tests.cmd (skip full rebuild header)" {
        # run_tests.cmd always rebuilds; here we only run the validation half.
        Invoke-Python @("tools/validate_yinyuan_source_consistency.py")
        Invoke-Python @(
            "-m", "unittest",
            "tests/yinjie/test_yinjie_encoder.py",
            "tests/yinjie/test_yinjie_decoder.py",
            "tests/yinjie/test_pinyin_bidirectional_validation.py",
            "tests/yinjie/test_yinjie_roundtrip.py",
            "tests/yinjie/test_yinjie_encoder_stages.py",
            "tests/yinjie/test_yinjie_entry_manifests.py",
            "tests/syllable_analysis/test_encode_ganyin.py",
            "tests/test_pinyin_normalizer.py"
        )
    }
}

# --- step 4: runtime integration (optional) ---
$baselineForReport = ""
if ($ApplyRuntime) {
    Invoke-Step "4/4 backup runtime DB -> $BaselineBackup" {
        if (-not (Test-Path $RuntimeDb)) {
            throw "Runtime DB not found: $RuntimeDb"
        }
        Copy-Item -Force $RuntimeDb $BaselineBackup
    }
    $baselineForReport = $BaselineBackup

    Invoke-Step "4/4 prototype import (single char + phrase)" {
        $env:YIME_SOURCE_PINYIN_DB = (Resolve-Path $TrialDb).Path
        try {
            Invoke-Python @("yime/import_danzi_into_prototype_tables.py")
            Invoke-Python @("yime/import_duozi_into_prototype_tables.py")
        } finally {
            Remove-Item Env:YIME_SOURCE_PINYIN_DB -ErrorAction SilentlyContinue
        }
    }

    Invoke-Step "4/4 refresh_runtime_yime_codes.py --apply" {
        Invoke-Python @("yime/refresh_runtime_yime_codes.py", "--apply")
    }

    Invoke-Step "4/4 export_runtime_candidates_json.py" {
        Invoke-Python @("yime/export_runtime_candidates_json.py")
    }
} else {
    Write-Step "4/4 runtime integration skipped (pass -ApplyRuntime to update pinyin_hanzi.db)"
}

# --- final report + encoding guard ---
Invoke-Step "final metrics report" {
    Write-Metrics `
        -SourceDbPath $TrialDb `
        -RuntimeDbPath $(if ($ApplyRuntime) { $RuntimeDb } else { "" }) `
        -BaselineRuntimeDbPath $baselineForReport `
        -RuntimeJsonPath $(if ($ApplyRuntime) { $RuntimeJson } else { "" })
}

if (-not $DryRun -and $encodingHashBefore) {
    $encodingHashAfter = (Get-FileHash $EncodingJson -Algorithm SHA256).Hash
    if ($encodingHashBefore -ne $encodingHashAfter) {
        throw "Encoding layer changed unexpectedly: $EncodingJson sha256 before=$encodingHashBefore after=$encodingHashAfter"
    }
    Write-Host "encoding guard OK: $EncodingJson unchanged" -ForegroundColor Green
}

Print-ReportSummary

Write-Host ""
Write-Host "Done." -ForegroundColor Green
if ($ApplyRuntime) {
    Write-Host "Product gate: python run_input_method.py"
    Write-Host "If refresh reported missing patches, see internal_data/pinyin_source_db/PATCH_POLICY.md"
    Write-Host "Rollback runtime DB: Copy-Item -Force '$BaselineBackup' '$RuntimeDb'"
} else {
    Write-Host "Next: inspect $ReportJson, then rerun with -ApplyRuntime"
}
