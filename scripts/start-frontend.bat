@echo off
REM ================================================================
REM Start Frontend (Production Build) — Arbitrage Bot
REM ================================================================
REM Asumsi: yarn install + yarn build sudah dijalankan
REM        Output ada di frontend\build
REM ================================================================

cd /d "%~dp0\..\frontend"

if not exist "build" (
    echo [ERROR] Folder build tidak ditemukan.
    echo Jalankan dulu:
    echo     cd frontend
    echo     yarn install
    echo     yarn build
    pause
    exit /b 1
)

REM Install global static server kalau belum ada
where serve >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing 'serve' globally...
    call yarn global add serve
)

echo.
echo ================================================================
echo  Serving frontend build on http://0.0.0.0:3000
echo  Press Ctrl+C to stop
echo ================================================================
echo.

serve -s build -l 3000
