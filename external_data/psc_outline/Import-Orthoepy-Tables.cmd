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

"%PYTHON%" "import_orthoepy_tables.py"
if errorlevel 1 pause
