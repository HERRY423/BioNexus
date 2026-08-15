@echo off
setlocal
echo ==============================================================================
echo  BioNexus Plugin: Windows One-Click Setup
echo ==============================================================================

where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python not found on PATH. Please install Python 3.10+ from python.org
    pause
    exit /b 1
)

if not exist ".venv" (
    echo [INFO] Creating Python virtual environment in .venv ...
    python -m venv .venv
)

echo [INFO] Activating virtual environment ...
call .venv\Scripts\activate.bat

python scripts\setup_env.py %*

echo.
echo Setup finished. You can activate the environment anytime via:
echo   call .venv\Scripts\activate.bat
echo.
pause
