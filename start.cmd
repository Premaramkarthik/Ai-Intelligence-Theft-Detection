@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem Antigravity Vision - Unified System Runner (Windows CMD)
rem This script starts all Backend Services and the Modern Frontend directly.

rem 0. Configuration
set "PROJECT_ROOT=%~dp0"
if "%PROJECT_ROOT:~-1%"=="\" set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"
set "BACKEND_DIR=%PROJECT_ROOT%\backend"
set "FRONTEND_DIR=%PROJECT_ROOT%\frontend"
set "LOGS_DIR=%PROJECT_ROOT%\logs"

if not exist "%LOGS_DIR%" mkdir "%LOGS_DIR%"
del /q "%LOGS_DIR%\*.log" 2>nul

rem 1. Start required infrastructure (Redis, Postgres, MQTT)
echo Starting Docker infrastructure services...
pushd "%BACKEND_DIR%"
docker compose up -d redis postgres mqtt
if errorlevel 1 (
    echo Error: Failed to start Docker infrastructure services.
    popd
    exit /b 1
)
popd

rem 2. Cleanup stale processes and ports
echo Performing system cleanup...
for %%P in (
    "services.signaling.main"
    "services.mediabridge.main"
    "services.inference.main"
    "services.alerting.main"
    "services.persistence.main"
    "npm run dev"
) do (
    powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*%%~P*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1
)

for %%P in (9001 8501 9101 9102 9103 9104) do (
    for /f %%I in ('powershell -NoProfile -Command "(Get-NetTCPConnection -LocalPort %%P -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique)"') do (
        if not "%%I"=="" (
            echo   ^> Killing stale process on port %%P (PID: %%I)
            taskkill /PID %%I /F >nul 2>&1
        )
    )
)

echo Clearing volatile state...
docker exec backend-redis-1 redis-cli -a karthikS9 flushall >nul 2>&1
del /q "%TEMP%\cam_*" 2>nul

rem 3. Setup Backend Environment (VENV)
set "VENV_PATH=%BACKEND_DIR%\.venv"
if not exist "%VENV_PATH%\Scripts" set "VENV_PATH=%BACKEND_DIR%\venv"
set "VENV_BIN=%VENV_PATH%\Scripts"

if not exist "%VENV_BIN%" (
    echo Error: Backend virtual environment not found at backend\.venv or backend\venv
    exit /b 1
)

rem 4. Start Backend Services
echo Launching Antigravity Vision Services...
pushd "%BACKEND_DIR%"
set "PYTHONPATH=%BACKEND_DIR%"

echo   ^> Signaling (API)...
for /f %%I in ('powershell -NoProfile -Command "$p = Start-Process -FilePath '%VENV_BIN%\uvicorn.exe' -ArgumentList 'services.signaling.main:app --host 0.0.0.0 --port 9001' -WorkingDirectory '%BACKEND_DIR%' -RedirectStandardOutput '%LOGS_DIR%\backend_signaling.log' -RedirectStandardError '%LOGS_DIR%\backend_signaling.log' -PassThru; $p.Id"') do set "SIG_PID=%%I"

echo   ^> MediaBridge (Capture)...
for /f %%I in ('powershell -NoProfile -Command "$env:PYTHONPATH='%BACKEND_DIR%'; $p = Start-Process -FilePath '%VENV_BIN%\python.exe' -ArgumentList '-m services.mediabridge.main' -WorkingDirectory '%BACKEND_DIR%' -RedirectStandardOutput '%LOGS_DIR%\backend_mediabridge.log' -RedirectStandardError '%LOGS_DIR%\backend_mediabridge.log' -PassThru; $p.Id"') do set "MB_PID=%%I"

echo   ^> Inference (AI)...
for /f %%I in ('powershell -NoProfile -Command "$env:PYTHONPATH='%BACKEND_DIR%'; $p = Start-Process -FilePath '%VENV_BIN%\python.exe' -ArgumentList '-m services.inference.main' -WorkingDirectory '%BACKEND_DIR%' -RedirectStandardOutput '%LOGS_DIR%\backend_inference.log' -RedirectStandardError '%LOGS_DIR%\backend_inference.log' -PassThru; $p.Id"') do set "INF_PID=%%I"

echo   ^> Alerting...
for /f %%I in ('powershell -NoProfile -Command "$env:PYTHONPATH='%BACKEND_DIR%'; $p = Start-Process -FilePath '%VENV_BIN%\python.exe' -ArgumentList '-m services.alerting.main' -WorkingDirectory '%BACKEND_DIR%' -RedirectStandardOutput '%LOGS_DIR%\backend_alerting.log' -RedirectStandardError '%LOGS_DIR%\backend_alerting.log' -PassThru; $p.Id"') do set "ALT_PID=%%I"

echo   ^> Persistence...
for /f %%I in ('powershell -NoProfile -Command "$env:PYTHONPATH='%BACKEND_DIR%'; $p = Start-Process -FilePath '%VENV_BIN%\python.exe' -ArgumentList '-m services.persistence.main' -WorkingDirectory '%BACKEND_DIR%' -RedirectStandardOutput '%LOGS_DIR%\backend_persistence.log' -RedirectStandardError '%LOGS_DIR%\backend_persistence.log' -PassThru; $p.Id"') do set "PER_PID=%%I"
popd

rem 5. Start Modern Frontend
echo   ^> Modern Dashboard (React)...
for /f %%I in ('powershell -NoProfile -Command "$p = Start-Process -FilePath 'npm.cmd' -ArgumentList 'run dev' -WorkingDirectory '%FRONTEND_DIR%' -RedirectStandardOutput '%LOGS_DIR%\frontend.log' -RedirectStandardError '%LOGS_DIR%\frontend.log' -PassThru; $p.Id"') do set "FRONT_PID=%%I"

echo ----------------------------------------------------
echo Antigravity Vision System is LIVE!
echo Modern Dashboard: http://localhost:3000
echo API Documentation: http://localhost:9001/docs
echo ----------------------------------------------------
echo All logs are in the "%LOGS_DIR%" folder.
echo Press Ctrl+C to stop all services.

rem 6. Lifecycle Management
powershell -NoProfile -Command ^
    "$ids = @(%SIG_PID%, %MB_PID%, %INF_PID%, %ALT_PID%, %PER_PID%, %FRONT_PID%) | Where-Object { $_ -and $_ -ne 0 }; try { Wait-Process -Id $ids } finally { foreach ($id in $ids) { Stop-Process -Id $id -Force -ErrorAction SilentlyContinue } }"
exit /b %errorlevel%
