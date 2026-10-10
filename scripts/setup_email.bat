@echo off
cd /d "%~dp0.."
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\setup_email.py
) else (
  python scripts\setup_email.py
)
pause