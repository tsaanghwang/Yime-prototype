@echo off
setlocal
cd /d "%~dp0"

set "PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not exist "%PYTHON%" (
    echo Codex bundled Python was not found:
    echo %PYTHON%
    pause
    exit /b 2
)

if not exist ".generated\orthoepy_coverage\orthoepy_coverage.sqlite3" (
    ".\venv312\Scripts\python.exe" "tools\audit_orthoepy_coverage.py"
    if errorlevel 1 pause & exit /b 1
)

"%PYTHON%" "tools\review_orthoepy_coverage.py"
if errorlevel 1 pause
