@echo off
REM Check if running as admin
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Requesting administrator privileges...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

cd /d "%~dp0"

REM Create venv and install dependencies if needed
if not exist ".venv\Scripts\activate.bat" (
    echo Creating virtual environment with uv...
    uv venv --python 3.13
    echo Installing dependencies...
    uv pip install -r requirements.txt
)

REM Activate virtual environment
call .venv\Scripts\activate.bat

REM Run the app
python main.py

pause
