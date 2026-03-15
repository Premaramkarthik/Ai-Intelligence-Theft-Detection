@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "PROJECT_ROOT=%~dp0"
if "%PROJECT_ROOT:~-1%"=="\" set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"

set "BACKEND_DIR=%PROJECT_ROOT%\backend"
set "BACKEND_CLEANUP_CMD=%BACKEND_DIR%\scripts\cleanup.cmd"

if not exist "%BACKEND_DIR%" (
    echo Error: backend directory not found at "%BACKEND_DIR%".
    exit /b 1
)

if not exist "%BACKEND_CLEANUP_CMD%" (
    echo Error: backend cleanup script not found at "%BACKEND_CLEANUP_CMD%".
    exit /b 1
)

echo Stopping frontend...
call :kill_title "pipeline-frontend"
call :kill_port 3000

echo Stopping backend services...
call "%BACKEND_CLEANUP_CMD%"
if errorlevel 1 (
    echo Error: backend cleanup failed.
    exit /b 1
)

echo.
echo Full local stack stopped.
exit /b 0

:kill_title
set "TARGET_TITLE=%~1"
taskkill /fi "WINDOWTITLE eq %TARGET_TITLE%" /t /f >nul 2>&1
if not errorlevel 1 (
    echo   ^>^> Stopped %TARGET_TITLE%
)
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
    if not errorlevel 1 (
        echo   ^>^> Killed process on port %TARGET_PORT% ^(PID: !FOUND_PID!^)
    )
)
exit /b 0
