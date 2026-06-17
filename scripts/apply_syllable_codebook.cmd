@echo off
setlocal

cd /d "%~dp0\.."

if exist "venv312\Scripts\python.exe" (
  set "PYTHON=venv312\Scripts\python.exe"
) else if exist ".venv\Scripts\python.exe" (
  set "PYTHON=.venv\Scripts\python.exe"
) else (
  set "PYTHON=python"
)

echo Phase 2: rebuild syllable codebook and encoding assets...
echo Run this only after lexicon export and unittest gate are green.
echo.

"%PYTHON%" tools\rebuild_encoding_assets.py
if errorlevel 1 exit /b %ERRORLEVEL%

"%PYTHON%" -m unittest ^
  tests\yinjie\test_pinyin_bidirectional_validation.py ^
  tests\yinjie\test_yinjie_roundtrip.py

exit /b %ERRORLEVEL%
