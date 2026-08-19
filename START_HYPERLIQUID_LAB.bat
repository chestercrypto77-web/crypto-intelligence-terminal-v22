@echo off
setlocal
cd /d "%~dp0"
if not exist ".env.local" (
  copy ".env.local.example" ".env.local" >nul
  echo Created .env.local. Put your existing DATABASE_URL in that file, save it, then run this again.
  start notepad ".env.local"
  pause
  exit /b 1
)
for /f "usebackq tokens=1,* delims==" %%A in (".env.local") do (
  if not "%%A"=="" if not "%%A:~0,1"=="#" set "%%A=%%B"
)
if "%DATABASE_URL%"=="" (
  echo DATABASE_URL is missing from .env.local
  pause
  exit /b 1
)
python -m pip install -r requirements-hyperliquid-lab.txt
if errorlevel 1 pause & exit /b 1
set "HL_EXECUTION_MODE=DISABLED"
set "HL_LAB_UNIVERSE=BTC,ETH,SOL,HYPE"
echo.
echo Starting Hyperliquid Trading Laboratory - MAINNET public data / execution DISABLED
echo Keep this window open. Press Ctrl+C to stop.
echo.
python scripts\v22_hyperliquid_lab.py
pause
