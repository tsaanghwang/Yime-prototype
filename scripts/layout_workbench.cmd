@echo off
setlocal
cd /d "%~dp0\.."

if exist "venv312\Scripts\pythonw.exe" (
  start "" "venv312\Scripts\pythonw.exe" tools\layout_workbench.py
) else if exist "venv312\Scripts\python.exe" (
  start "" "venv312\Scripts\python.exe" tools\layout_workbench.py
) else (
  start "" pythonw tools\layout_workbench.py
)
