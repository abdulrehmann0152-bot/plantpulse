@echo off
title PlantPulse Tests
cd /d "%~dp0"
if exist "venv\Scripts\activate.bat" (
  call venv\Scripts\activate.bat
) else if exist "..\venv\Scripts\activate.bat" (
  call ..\venv\Scripts\activate.bat
) else (
  echo Could not find the venv folder. Run setup_plantpulse.bat first.
  pause
  exit /b 1
)
python -m pytest -v
pause
