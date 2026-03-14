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
start "pipeline-signaling" /min cmd /d /c ""cd /d "%BACKEND_DIR%" ^&^& "%PYTHON_EXE%" -m uvicorn services.signaling.main:app --host 0.0.0.0 --port 9001 1^>^> "%LOGS_DIR%\signaling.log" 2^>^&1""

echo   ^>^> MediaBridge (Capture)...
start "pipeline-mediabridge" /min cmd /d /c ""cd /d "%BACKEND_DIR%" ^&^& "%PYTHON_EXE%" -m services.mediabridge.main 1^>^> "%LOGS_DIR%\mediabridge.log" 2^>^&1""

echo   ^>^> Inference (AI)...
start "pipeline-inference" /min cmd /d /c ""cd /d "%BACKEND_DIR%" ^&^& "%PYTHON_EXE%" -m services.inference.main 1^>^> "%LOGS_DIR%\inference.log" 2^>^&1""

echo   ^>^> Alerting...
start "pipeline-alerting" /min cmd /d /c ""cd /d "%BACKEND_DIR%" ^&^& "%PYTHON_EXE%" -m services.alerting.main 1^>^> "%LOGS_DIR%\alerting.log" 2^>^&1""

echo   ^>^> Persistence...
start "pipeline-persistence" /min cmd /d /c ""cd /d "%BACKEND_DIR%" ^&^& "%PYTHON_EXE%" -m services.persistence.main 1^>^> "%LOGS_DIR%\persistence.log" 2^>^&1""

echo All services started.
echo Check logs folder for output: "%LOGS_DIR%"
echo Run "%SCRIPT_DIR%cleanup.cmd" to stop the services.

exit /b 0
