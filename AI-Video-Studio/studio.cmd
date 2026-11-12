@echo off
REM Windows launcher: studio make "..." etc. Uses the project's virtual environment.
setlocal
set "HERE=%~dp0"
if exist "%HERE%.venv\Scripts\python.exe" (
  "%HERE%.venv\Scripts\python.exe" "%HERE%studio.py" %*
) else (
  echo Virtual environment missing. Run windows\setup.ps1 first.
  exit /b 1
)
