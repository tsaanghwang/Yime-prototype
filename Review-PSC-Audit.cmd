@echo off
setlocal
cd /d "%~dp0"

if not exist ".generated\psc_pronunciation_audit\psc_pronunciation_audit.sqlite3" (
    echo PSC audit database was not found.
    echo Run tools\audit_psc_pronunciation_source.py first.
    pause
    exit /b 2
)

set "PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not exist "%PYTHON%" (
    echo Codex bundled Python was not found:
    echo %PYTHON%
    pause
    exit /b 2
)

"%PYTHON%" "tools\review_psc_pronunciation_audit.py"
if errorlevel 1 pause
