# 恢复完整数据链路（按 docs/project/PINYIN_DATA_MIGRATION.md + scripts/run_tests.cmd）
#
# 用法:
#   .\scripts\restore_full_pipeline.ps1 -Mode pre-rebuild   # 恢复 rebuild 前 IME 可用的运行时 DB
#   .\scripts\restore_full_pipeline.ps1 -Mode forward         # 简化 forward（无备份/报告）
#   .\scripts\integrate_lexicon_trial.ps1 -ApplyRuntime      # 推荐：trial 词库接入 + 备份 + 报告
#   .\scripts\restore_full_pipeline.ps1 -Mode lexicon-only  # 只跑词库层 + run_tests（不动 runtime DB）
#
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
    Invoke-Step "restore runtime DB from HEAD copy" {
        if (-not (Test-Path "yime/pinyin_hanzi.db.from_head")) {
            Write-Host "Pulling yime/pinyin_hanzi.db from git LFS..."
            git lfs pull --include="yime/pinyin_hanzi.db"
            $oid = (git lfs ls-files -l yime/pinyin_hanzi.db 2>$null | ForEach-Object { ($_ -split '\s+')[0] })
            if ($oid) {
                $src = ".git/lfs/objects/$($oid.Substring(0,2))/$($oid.Substring(2,2))/$oid"
                if (Test-Path $src) { Copy-Item $src "yime/pinyin_hanzi.db.from_head" -Force }
            }
        }
        if (-not (Test-Path "yime/pinyin_hanzi.db.from_head")) {
            throw "yime/pinyin_hanzi.db.from_head not found; close IDE DB tabs and run git lfs pull"
        }
        if (Test-Path "yime/pinyin_hanzi.db") {
            Move-Item -Force "yime/pinyin_hanzi.db" "yime/pinyin_hanzi.db.post_rebuild.bak"
        }
        Move-Item -Force "yime/pinyin_hanzi.db.from_head" "yime/pinyin_hanzi.db"
    }

    Invoke-Step "restore encoding JSON from HEAD" {
        git restore --source=HEAD -- `
            syllable/codec/yinjie_code.json `
            yime/pinyin_normalized.json `
            yime/code_pinyin.json `
            internal_data/pinyin_source_db/lexicon_exports/pinyin_normalized.json
    }

    Invoke-Step "export runtime candidates JSON" {
        python yime/export_runtime_candidates_json.py
    }
}
elseif ($Mode -eq "forward") {
    Invoke-Step "rebuild lexicon exports (phase 1)" {
        python internal_data/pinyin_source_db/rebuild_pinyin_assets.py
    }
    Invoke-Step "prototype import + runtime refresh" {
        python yime/import_danzi_into_prototype_tables.py
        python yime/import_duozi_into_prototype_tables.py
        python yime/refresh_runtime_yime_codes.py --apply
        python yime/export_runtime_candidates_json.py
    }
}
else {
    Invoke-Step "rebuild lexicon exports (phase 1)" {
        python internal_data/pinyin_source_db/rebuild_pinyin_assets.py
    }
}

Invoke-Step "run_tests.cmd (lexicon + encoding validation)" {
    cmd /c scripts\run_tests.cmd
}

Write-Host "`nDone ($Mode). Next: python run_input_method.py" -ForegroundColor Green
