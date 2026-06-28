@echo off
REM ================================================================
REM Install Arbitrage Bot as Windows Services via NSSM
REM ================================================================
REM Prasyarat:
REM   1. Install NSSM: https://nssm.cc/download
REM      Extract & taruh nssm.exe di C:\nssm\ atau di PATH
REM   2. Backend venv sudah dibuat & dependencies installed
REM   3. Frontend sudah di-build (yarn build)
REM   4. MongoDB service jalan
REM ================================================================
REM Run AS ADMINISTRATOR (right-click -> Run as administrator)
REM ================================================================

setlocal

REM === Konfigurasi (edit jika perlu) ===
set NSSM=nssm.exe
set BACKEND_NAME=ArbitrageBackend
set FRONTEND_NAME=ArbitrageFrontend
set ROOT_DIR=%~dp0..
set BACKEND_DIR=%ROOT_DIR%\backend
set FRONTEND_DIR=%ROOT_DIR%\frontend
set PYTHON_EXE=%BACKEND_DIR%\venv\Scripts\python.exe
set NODE_EXE=

REM === Cek NSSM tersedia ===
where %NSSM% >nul 2>&1
if errorlevel 1 (
    echo [ERROR] nssm.exe tidak ditemukan di PATH.
    echo Download dari https://nssm.cc/download dan extract ke C:\nssm\
    echo lalu tambahkan ke PATH atau pindahkan nssm.exe ke folder Windows.
    pause
    exit /b 1
)

REM === Cek admin rights ===
net session >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Script ini harus dijalankan sebagai Administrator.
    pause
    exit /b 1
)

REM === Cek file penting ===
if not exist "%PYTHON_EXE%" (
    echo [ERROR] Python venv tidak ditemukan: %PYTHON_EXE%
    echo Jalankan setup backend dulu (lihat README).
    pause
    exit /b 1
)

if not exist "%FRONTEND_DIR%\build" (
    echo [ERROR] Frontend build tidak ditemukan: %FRONTEND_DIR%\build
    echo Jalankan: cd frontend ^&^& yarn install ^&^& yarn build
    pause
    exit /b 1
)

REM === Hapus service lama kalau sudah ada (clean install) ===
%NSSM% stop %BACKEND_NAME% >nul 2>&1
%NSSM% remove %BACKEND_NAME% confirm >nul 2>&1
%NSSM% stop %FRONTEND_NAME% >nul 2>&1
%NSSM% remove %FRONTEND_NAME% confirm >nul 2>&1

REM === Install Backend Service ===
echo.
echo [INFO] Installing service: %BACKEND_NAME%
%NSSM% install %BACKEND_NAME% "%PYTHON_EXE%" "-m uvicorn server:app --host 0.0.0.0 --port 8001"
%NSSM% set %BACKEND_NAME% AppDirectory "%BACKEND_DIR%"
%NSSM% set %BACKEND_NAME% Description "Arbitrage Bot FastAPI backend"
%NSSM% set %BACKEND_NAME% Start SERVICE_AUTO_START
%NSSM% set %BACKEND_NAME% AppStdout "%BACKEND_DIR%\backend.out.log"
%NSSM% set %BACKEND_NAME% AppStderr "%BACKEND_DIR%\backend.err.log"
%NSSM% set %BACKEND_NAME% AppRotateFiles 1
%NSSM% set %BACKEND_NAME% AppRotateBytes 10485760

REM === Install Frontend Service ===
echo [INFO] Installing service: %FRONTEND_NAME%
where serve >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing 'serve' globally...
    call yarn global add serve
)
for /f "delims=" %%i in ('where serve 2^>nul') do set SERVE_CMD=%%i
if "%SERVE_CMD%"=="" (
    echo [ERROR] Tidak bisa menemukan command 'serve'. Install manual: yarn global add serve
    pause
    exit /b 1
)

%NSSM% install %FRONTEND_NAME% "%SERVE_CMD%" "-s build -l 3000"
%NSSM% set %FRONTEND_NAME% AppDirectory "%FRONTEND_DIR%"
%NSSM% set %FRONTEND_NAME% Description "Arbitrage Bot Frontend (React build)"
%NSSM% set %FRONTEND_NAME% Start SERVICE_AUTO_START
%NSSM% set %FRONTEND_NAME% AppStdout "%FRONTEND_DIR%\frontend.out.log"
%NSSM% set %FRONTEND_NAME% AppStderr "%FRONTEND_DIR%\frontend.err.log"

REM === Start services ===
echo.
echo [INFO] Starting services...
%NSSM% start %BACKEND_NAME%
%NSSM% start %FRONTEND_NAME%

echo.
echo ================================================================
echo  SUCCESS - Services installed and started
echo ================================================================
echo  Backend  : http://localhost:8001  (service: %BACKEND_NAME%)
echo  Frontend : http://localhost:3000  (service: %FRONTEND_NAME%)
echo.
echo  Manage services:
echo    nssm start ^| stop ^| restart ^| status ^| remove %BACKEND_NAME%
echo    nssm start ^| stop ^| restart ^| status ^| remove %FRONTEND_NAME%
echo.
echo  Cek juga via services.msc
echo ================================================================
pause
