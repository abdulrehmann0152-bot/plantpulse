@echo off
title PlantPulse
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
if not exist "%USERPROFILE%\.streamlit\credentials.toml" (
  mkdir "%USERPROFILE%\.streamlit" 2>nul
  (echo [general]& echo email = "") > "%USERPROFILE%\.streamlit\credentials.toml"
)
echo Starting PlantPulse... your browser will open. Close this window to stop the app.
streamlit run app.py
pause
