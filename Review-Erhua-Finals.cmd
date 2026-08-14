@echo off
setlocal
cd /d "%~dp0"

if not exist "external_data\tmp\final_styles_erhua_draft.json" (
    echo Erhua working draft was not found:
    echo external_data\tmp\final_styles_erhua_draft.json
    pause
    exit /b 2
)

set "PYTHON=%~dp0venv312\Scripts\python.exe"
if not exist "%PYTHON%" (
    set "PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
)
if not exist "%PYTHON%" (
    echo Python runtime was not found.
    pause
    exit /b 2
)

"%PYTHON%" "tools\review_erhua_final_segments.py"
if errorlevel 1 pause
