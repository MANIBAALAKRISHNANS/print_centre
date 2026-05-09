@echo off
:: PrintHub Agent - Windows Service Installer
:: Run as Administrator
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo ===========================================================
echo  PrintHub Print Agent - Windows Installer
echo ===========================================================
echo.

:: Check Administrator privileges
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] This script must be run as Administrator.
    echo         Right-click and select "Run as administrator"
    pause & exit /b 1
)
echo [OK] Running as Administrator.

:: Check Python
python --version >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] Python 3.11+ is not installed or not in PATH.
    echo         Download: https://www.python.org/downloads/
    pause & exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo [OK] Python %PY_VER% found.

:: Create virtual environment if needed
if not exist "venv\Scripts\python.exe" (
    echo [STEP 1] Creating virtual environment...
    python -m venv venv
    if %errorLevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause & exit /b 1
    )
    echo [OK] Virtual environment created.
) else (
    echo [OK] Virtual environment ready.
)

:: Use venv python directly - no activation needed
set VENV_PY=%~dp0venv\Scripts\python.exe
set VENV_PIP=%~dp0venv\Scripts\pip.exe

:: Verify venv python exists
if not exist "%VENV_PY%" (
    echo [ERROR] venv\Scripts\python.exe not found. Deleting and recreating venv...
    rmdir /s /q venv
    python -m venv venv
    if %errorLevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause & exit /b 1
    )
)

:: Install dependencies using full path to venv pip
echo [STEP 2] Installing dependencies...
"%VENV_PY%" -m pip install --quiet --upgrade pip
"%VENV_PY%" -m pip install --quiet -r requirements.txt
if %errorLevel% neq 0 (
    echo [ERROR] Dependency installation failed.
    echo         Check your internet connection and try again.
    pause & exit /b 1
)
echo [OK] Dependencies installed (including websocket-client for real-time).

:: Run pywin32 post-install (required for Windows Service support)
"%VENV_PY%" -c "import win32serviceutil" >nul 2>&1
if %errorLevel% neq 0 (
    echo [INFO] Running pywin32 post-install...
    for /f "delims=" %%i in ('"%VENV_PY%" -c "import sys; print(sys.prefix)"') do set VENV_PREFIX=%%i
    "%VENV_PY%" "!VENV_PREFIX!\Scripts\pywin32_postinstall.py" -install >nul 2>&1
)

:: First-time setup
if not exist "agent_config.json" (
    echo.
    echo ===========================================================
    echo  SETUP - Connect this workstation to PrintHub Server
    echo ===========================================================
    echo.
    set /p SERVER_IP="  Server IP address (e.g. 192.168.1.50): "
    set /p SERVER_PORT="  Server port (press Enter for 8000): "
    if "!SERVER_PORT!"=="" set SERVER_PORT=8000

    set /p USE_HTTPS="  Use HTTPS? (y/N): "
    if /i "!USE_HTTPS!"=="y" (
        set PROTO=https
        set /p SKIP_VERIFY="  Skip TLS cert check for self-signed cert? (y/N): "
        if /i "!SKIP_VERIFY!"=="y" (set NV_FLAG=--no-verify) else (set NV_FLAG=)
    ) else (
        set PROTO=http
        set NV_FLAG=
    )
    set SERVER_URL=!PROTO!://!SERVER_IP!:!SERVER_PORT!

    echo.
    echo  Go to PrintHub Dashboard ^> Agents ^> Generate Code
    set /p ACT_CODE="  Enter the 8-character activation code: "

    echo.
    echo  Saving configuration for !SERVER_URL!...
    "%VENV_PY%" agent_setup.py --code !ACT_CODE! --server !SERVER_URL! !NV_FLAG!
    if %errorLevel% neq 0 (
        echo [ERROR] Setup failed. Check the activation code and server URL.
        pause & exit /b 1
    )
    echo [OK] Configuration saved.
) else (
    echo [OK] Existing configuration found - skipping setup.
)

:: Stop and remove existing service if running
sc query PrintHubAgent >nul 2>&1
if %errorLevel% equ 0 (
    echo [STEP 3] Removing existing service...
    "%VENV_PY%" agent_service.py stop >nul 2>&1
    timeout /t 2 /nobreak >nul
    "%VENV_PY%" agent_service.py remove >nul 2>&1
    timeout /t 2 /nobreak >nul
)

:: Install Windows Service
echo [STEP 3] Installing Windows Service (PrintHubAgent)...
"%VENV_PY%" agent_service.py --startup auto install
if %errorLevel% neq 0 (
    echo [ERROR] Service installation failed.
    echo         Check the log: %~dp0venv\Scripts\pywin32_postinstall.py
    pause & exit /b 1
)
echo [OK] Service installed.

:: Start the service
echo [STEP 4] Starting service...
"%VENV_PY%" agent_service.py start
if %errorLevel% neq 0 (
    echo [WARNING] Service did not start cleanly.
    echo           Check: C:\PrintHubAgent\agent_service.log
) else (
    echo [OK] Service started.
)

:: Wait and verify
timeout /t 4 /nobreak >nul
sc query PrintHubAgent | findstr "RUNNING" >nul 2>&1
if %errorLevel% equ 0 (
    echo.
    echo ===========================================================
    echo  SUCCESS! PrintHub Agent is running as a Windows Service.
    echo  It starts automatically on every boot.
    echo.
    echo  Logs:
    echo    C:\PrintHubAgent\agent.log
    echo    C:\PrintHubAgent\agent_service.log
    echo.
    echo  Commands (run from this folder):
    echo    venv\Scripts\python.exe agent_service.py stop
    echo    venv\Scripts\python.exe agent_service.py start
    echo    venv\Scripts\python.exe agent_service.py restart
    echo    venv\Scripts\python.exe agent_service.py remove
    echo    venv\Scripts\python.exe agent_setup.py --status
    echo ===========================================================
) else (
    echo.
    echo [WARNING] Service may not have started correctly.
    echo Check: C:\PrintHubAgent\agent_service.log
    echo Or run manually to see errors:
    echo   venv\Scripts\python.exe agent.py
)

echo.
pause
