@echo off
cd /d "%~dp0"
where pythonw >nul 2>nul
if not errorlevel 1 (
    start "" pythonw "%~dp0main.py"
    exit /b
)
python "%~dp0main.py"
if errorlevel 1 pause
