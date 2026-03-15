@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "BACKEND_DIR=%%~fI"
for %%I in ("%BACKEND_DIR%\..") do set "PROJECT_ROOT=%%~fI"
set "LOGS_DIR=%PROJECT_ROOT%\logs"
set "CLEANUP_CMD=%SCRIPT_DIR%cleanup.cmd"

echo Starting Docker infrastructure services...
pushd "%BACKEND_DIR%"
docker compose up -d redis postgres mqtt
if errorlevel 1 (
    popd
    echo Error: failed to start Docker infrastructure services.
    exit /b 1
)
popd

call "%CLEANUP_CMD%"
if errorlevel 1 (
    echo Error: cleanup failed.
    exit /b 1
)

set "VENV_SCRIPTS=%PROJECT_ROOT%\.venv\Scripts"
if not exist "%VENV_SCRIPTS%" set "VENV_SCRIPTS=%PROJECT_ROOT%\venv\Scripts"
if not exist "%VENV_SCRIPTS%" set "VENV_SCRIPTS=%BACKEND_DIR%\.venv\Scripts"
if not exist "%VENV_SCRIPTS%" set "VENV_SCRIPTS=%BACKEND_DIR%\venv\Scripts"

if not exist "%VENV_SCRIPTS%\python.exe" (
    echo Error: Virtual environment not found at .venv or venv.
    exit /b 1
)

echo Starting Pipeline OpenCV Services locally (using %VENV_SCRIPTS%)...

if not exist "%LOGS_DIR%" mkdir "%LOGS_DIR%"
del /q "%LOGS_DIR%\*.log" 2>nul

set "PYTHONPATH=%BACKEND_DIR%"
set "PYTHON_EXE=%VENV_SCRIPTS%\python.exe"

echo   ^>^> Signaling (API)...
call :start_service "pipeline-signaling" "-m uvicorn services.signaling.main:app --host 0.0.0.0 --port 9001" "%LOGS_DIR%\signaling.log"
if errorlevel 1 exit /b 1

echo   ^>^> MediaBridge (Capture)...
call :start_service "pipeline-mediabridge" "-m services.mediabridge.main" "%LOGS_DIR%\mediabridge.log"
if errorlevel 1 exit /b 1

echo   ^>^> Inference (AI)...
call :start_service "pipeline-inference" "-m services.inference.main" "%LOGS_DIR%\inference.log"
if errorlevel 1 exit /b 1

echo   ^>^> Alerting...
call :start_service "pipeline-alerting" "-m services.alerting.main" "%LOGS_DIR%\alerting.log"
if errorlevel 1 exit /b 1

echo   ^>^> Persistence...
call :start_service "pipeline-persistence" "-m services.persistence.main" "%LOGS_DIR%\persistence.log"
if errorlevel 1 exit /b 1

echo All services started.
echo Check logs folder for output: "%LOGS_DIR%"
echo Run "%SCRIPT_DIR%cleanup.cmd" to stop the services.

exit /b 0

:start_service
set "SERVICE_TITLE=%~1"
set "SERVICE_ARGS=%~2"
set "SERVICE_LOG=%~3"
set "SERVICE_ERR_LOG=%~dpn3.err.log"
set "SERVICE_OUT_LOG=%~dpn3.out.log"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$env:PYTHONPATH='%BACKEND_DIR%';" ^
    "$p = Start-Process -WindowStyle Minimized -FilePath '%PYTHON_EXE%' -ArgumentList '%SERVICE_ARGS%' -WorkingDirectory '%BACKEND_DIR%' -RedirectStandardOutput '%SERVICE_OUT_LOG%' -RedirectStandardError '%SERVICE_ERR_LOG%' -PassThru;" ^
    "if (-not $p) { exit 1 }"
if errorlevel 1 (
    echo Error: failed to launch %SERVICE_TITLE%.
    exit /b 1
)
exit /b 0
