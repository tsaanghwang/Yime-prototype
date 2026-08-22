@echo off
setlocal

set "PYTHONW=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe"
if not exist "%PYTHONW%" (
    echo Codex bundled Python was not found:
    echo %PYTHONW%
    echo.
    echo Open this folder in Codex and ask it to refresh the launcher.
    pause
    exit /b 2
)

set "DATABASE=%~1"
if not defined DATABASE set "DATABASE=%~dp0psc_outline_ocr.sqlite3"

if not exist "%DATABASE%" (
    echo Database was not found:
    echo %DATABASE%
    pause
    exit /b 2
)

start "PSC Outline Review" "%PYTHONW%" "%~dp0psc_outline_review_tool.py" "%DATABASE%" --image-dir "%~dp0pages"
exit /b 0
