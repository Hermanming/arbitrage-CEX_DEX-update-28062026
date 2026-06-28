@echo off
REM ================================================================
REM Start Backend (FastAPI) — Arbitrage Bot
REM ================================================================
REM Asumsi: virtual env sudah dibuat di backend\venv
REM        .env sudah disiapkan dengan MONGO_URL & FERNET_KEY
REM ================================================================

cd /d "%~dp0\..\backend"

if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] Virtual env tidak ditemukan di backend\venv
    echo Jalankan dulu:
    echo     cd backend
    echo     python -m venv venv
    echo     venv\Scripts\activate
    echo     pip install -r requirements.txt
    pause
    exit /b 1
)

if not exist ".env" (
    echo [ERROR] File .env tidak ditemukan di backend\.env
    echo Copy .env.example ke .env lalu isi nilainya.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

echo.
echo ================================================================
echo  Starting FastAPI backend on 0.0.0.0:8001
echo  Press Ctrl+C to stop
echo ================================================================
echo.

python -m uvicorn server:app --host 0.0.0.0 --port 8001
