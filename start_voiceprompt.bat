@echo off
REM Use Windows "py" launcher so you get the same Python where packages were installed.
cd /d "%~dp0"

echo Installing / updating dependencies (safe to run every time)...
py -3 -m pip install -r requirements.txt
if errorlevel 1 (
  echo pip failed. If you do not have Python, install from https://www.python.org/downloads/
  pause
  exit /b 1
)

echo.
echo Starting VoicePrompt (console — type HELP at voice-prompt ^> )...
py -3 app.py
pause
