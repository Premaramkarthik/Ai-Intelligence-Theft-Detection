@echo off
setlocal EnableExtensions EnableDelayedExpansion

echo Stopping Pipeline OpenCV services...

call :kill_title "pipeline-signaling"
call :kill_title "pipeline-mediabridge"
call :kill_title "pipeline-inference"
call :kill_title "pipeline-alerting"
call :kill_title "pipeline-persistence"

call :kill_port 9001
call :kill_port 9101
call :kill_port 9102
call :kill_port 9103
call :kill_port 9104

echo Cleanup complete. You can now run run_local.cmd
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
