# Unified lexicon -> syllable encoding -> runtime maintenance entry point.
param(
    [ValidateSet("pre-rebuild", "forward", "lexicon-only")]
    [string]$Mode = "pre-rebuild"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

function Invoke-Step([string]$Name, [scriptblock]$Block) {
    Write-Host "`n=== $Name ===" -ForegroundColor Cyan
    & $Block
    if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE"
    }
}

if ($Mode -eq "pre-rebuild") {
    Invoke-Step "restore tracked runtime assets" {
        & "$PSScriptRoot/restore_pre_rebuild_runtime.ps1"
    }
}
elseif ($Mode -eq "forward") {
    Invoke-Step "rebuild unified source and syllable exports" {
        python internal_data/pinyin_source_db/rebuild_pinyin_assets.py
    }
    Invoke-Step "rewrite prototype and runtime" {
        python -m yime.import_danzi_into_prototype_tables
        python -m yime.import_duozi_into_prototype_tables
        python -m yime.refresh_runtime_yime_codes --apply
        python -m yime.export_runtime_candidates_json
    }
}
else {
    Invoke-Step "rebuild unified source and syllable exports" {
        python internal_data/pinyin_source_db/rebuild_pinyin_assets.py
    }
}

Invoke-Step "lexicon and encoding validation" {
    cmd /c scripts\run_tests.cmd
}

Write-Host "`nDone ($Mode)." -ForegroundColor Green
