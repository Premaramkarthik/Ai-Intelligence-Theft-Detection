@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "PROJECT_ROOT=%~dp0"
if "%PROJECT_ROOT:~-1%"=="\" set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"

set "BACKEND_DIR=%PROJECT_ROOT%\backend"
set "FRONTEND_DIR=%PROJECT_ROOT%\frontend"
set "LOGS_DIR=%PROJECT_ROOT%\logs"
set "BACKEND_START_CMD=%BACKEND_DIR%\scripts\run_local.cmd"
set "BACKEND_CLEANUP_CMD=%BACKEND_DIR%\scripts\cleanup.cmd"
set "FRONTEND_OUT_LOG=%LOGS_DIR%\frontend.out.log"
set "FRONTEND_ERR_LOG=%LOGS_DIR%\frontend.err.log"

if not exist "%BACKEND_DIR%" (
    echo Error: backend directory not found at "%BACKEND_DIR%".
    exit /b 1
)

if not exist "%FRONTEND_DIR%" (
    echo Error: frontend directory not found at "%FRONTEND_DIR%".
    exit /b 1
)

if not exist "%BACKEND_START_CMD%" (
    echo Error: backend runner not found at "%BACKEND_START_CMD%".
    exit /b 1
)

if not exist "%BACKEND_CLEANUP_CMD%" (
    echo Error: backend cleanup script not found at "%BACKEND_CLEANUP_CMD%".
    exit /b 1
)

if not exist "%FRONTEND_DIR%\package.json" (
    echo Error: frontend package.json not found.
    exit /b 1
)

where npm.cmd >nul 2>&1
if errorlevel 1 (
    echo Error: npm.cmd is not available in PATH.
    exit /b 1
)

if not exist "%LOGS_DIR%" mkdir "%LOGS_DIR%"
del /q "%FRONTEND_OUT_LOG%" 2>nul
del /q "%FRONTEND_ERR_LOG%" 2>nul

echo Cleaning stale frontend processes...
call :kill_title "pipeline-frontend"
call :kill_port 3000

echo Starting backend stack...
call "%BACKEND_START_CMD%"
if errorlevel 1 (
    echo Error: backend stack failed to start.
    exit /b 1
)

echo Starting frontend...
call :start_frontend
if errorlevel 1 (
    echo Error: failed to launch frontend.
    exit /b 1
)

echo.
echo Full local stack started.
echo Frontend:  http://localhost:3000
echo API Docs:  http://localhost:9001/docs
echo Logs:      "%LOGS_DIR%"
echo.
echo Backend services started by "%BACKEND_START_CMD%":
echo   - signaling API
echo   - mediabridge
echo   - inference
echo   - alerting
echo   - persistence
echo Frontend logs:
echo   - %FRONTEND_OUT_LOG%
echo   - %FRONTEND_ERR_LOG%
echo.
echo Run "%BACKEND_CLEANUP_CMD%" to stop backend services.
echo Stop the frontend with: taskkill /fi "WINDOWTITLE eq pipeline-frontend" /t /f
exit /b 0

:kill_title
set "TARGET_TITLE=%~1"
taskkill /fi "WINDOWTITLE eq %TARGET_TITLE%" /t /f >nul 2>&1
exit /b 0

:kill_port
set "TARGET_PORT=%~1"
set "FOUND_PID="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /r /c:":%TARGET_PORT% .*LISTENING"') do (
    set "FOUND_PID=%%P"
    goto :kill_port_pid
)
exit /b 0

:kill_port_pid
if defined FOUND_PID (
    taskkill /pid !FOUND_PID! /t /f >nul 2>&1
)
exit /b 0

:start_frontend
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$p = Start-Process -WindowStyle Minimized -FilePath 'npm.cmd' -ArgumentList 'run dev' -WorkingDirectory '%FRONTEND_DIR%' -RedirectStandardOutput '%FRONTEND_OUT_LOG%' -RedirectStandardError '%FRONTEND_ERR_LOG%' -PassThru;" ^
    "if (-not $p) { exit 1 }"
if errorlevel 1 exit /b 1
exit /b 0
