@echo off
REM DiskGuard Pro 2.0 - installazione e avvio su Windows 11
REM Eseguire come Amministratore per funzioni complete
title DiskGuard Pro 2.0 - Setup
python --version >nul 2>&1
if errorlevel 1 (
  echo [ERRORE] Python non trovato. Installa Python 3.10+ da https://www.python.org/downloads/
  echo Ricorda di spuntare "Add python.exe to PATH".
  pause
  exit /b 1
)
echo Installazione dipendenze...
pip install --upgrade pip
pip install customtkinter psutil Pillow wmi pywin32
echo.
echo ============================================================
echo  DiskGuard Pro 2.0 pronto. Avvio...
echo  Suggerito: smartmontools da https://www.smartmontools.org
echo ============================================================
python app.py
pause
