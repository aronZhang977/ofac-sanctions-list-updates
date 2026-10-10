@echo off
cd /d "%~dp0.."
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\setup_config.py
) else (
  python scripts\setup_config.py
)
pause
