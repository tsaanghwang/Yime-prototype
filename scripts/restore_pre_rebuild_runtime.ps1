# 回退 rebuild_pinyin_assets.py 运行前的运行时资产（需先关闭 IDE 里打开的 .db）
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

Write-Host "Restoring tracked runtime files from HEAD..."
git restore --source=HEAD -- `
  yime/pinyin_hanzi.db `
  yime/pinyin_normalized.json `
  syllable/codec/yinjie_code.json `
  internal_data/pinyin_source_db/lexicon_exports/pinyin_normalized.json `
  internal_data/pinyin_source_db/rebuild_summary.json `
  internal_data/pinyin_source_db/validation_report.json `
  yime/input_method/core/runtime_ranking.py `
  yime/utils/runtime_codes_refresh.py `
  internal_data/pinyin_source_db/rebuild_pinyin_assets.py `
  yime/utils/prototype_single_char_import.py `
  yime/utils/prototype_phrase_import.py

Write-Host "Pulling LFS pinyin_hanzi.db..."
git lfs pull --include="yime/pinyin_hanzi.db"

$remove = @(
  ".generated/runtime_candidates_by_code_true.json"
)
foreach ($path in $remove) {
  if (Test-Path $path) {
    Remove-Item -Force $path
    Write-Host "Removed $path"
  }
}

if (Test-Path "yime/pinyin_hanzi.db.from_head") {
  Remove-Item -Force "yime/pinyin_hanzi.db.from_head"
}

Write-Host "Done. Verify with: python -c ""import sqlite3; c=sqlite3.connect('yime/pinyin_hanzi.db'); print(c.execute('SELECT COUNT(*) FROM single_char_readings').fetchone())"""
