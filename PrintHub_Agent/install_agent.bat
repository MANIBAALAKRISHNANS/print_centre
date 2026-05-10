@echo off
:: PrintHub Agent - Windows Installer (Task Scheduler)
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

set INSTALL_DIR=C:\PrintHubAgent

echo [STEP 1] Preparing installation directory %INSTALL_DIR%...
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

:: Copy all agent files to the install directory
echo [INFO] Copying agent files...
for %%f in (agent.py agent_service.py agent_config.py agent_setup.py requirements.txt) do (
    if exist "%~dp0%%f" (
        copy /y "%~dp0%%f" "%INSTALL_DIR%\%%f" >nul
    ) else (
        echo [WARNING] %%f not found in source folder - skipping
    )
)
if exist "%~dp0agent_macos.py" copy /y "%~dp0agent_macos.py" "%INSTALL_DIR%\agent_macos.py" >nul
echo [OK] Agent files copied to %INSTALL_DIR%

cd /d "%INSTALL_DIR%"

set VENV_PY=%INSTALL_DIR%\venv\Scripts\python.exe

:: Create virtual environment
if not exist "venv\Scripts\python.exe" (
    echo [STEP 2] Creating virtual environment...
    python -m venv venv
    if %errorLevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause & exit /b 1
    )
    echo [OK] Virtual environment created.
) else (
    echo [OK] Virtual environment ready.
)

:: Install dependencies
echo [STEP 3] Installing dependencies...
"%VENV_PY%" -m pip install --quiet --upgrade pip
"%VENV_PY%" -m pip install --quiet -r requirements.txt
if %errorLevel% neq 0 (
    echo [ERROR] Dependency installation failed. Check internet connection.
    pause & exit /b 1
)
echo [OK] Dependencies installed.

:: Run pywin32 post-install (required for win32print printer access)
echo [INFO] Running pywin32 post-install...
"%VENV_PY%" "%INSTALL_DIR%\venv\Scripts\pywin32_postinstall.py" -install
if %errorLevel% neq 0 (
    echo [WARNING] pywin32 post-install returned an error - printer access may not work
) else (
    echo [OK] pywin32 post-install complete.
)

:: First-time setup (only if no config exists)
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

:: ============================================================
:: Use Windows Task Scheduler (not Windows Service).
:: Task Scheduler runs as the current logged-on user, who has
:: Python/Anaconda in PATH. This avoids all SYSTEM account
:: issues with DLL loading that affect Windows Services.
:: ============================================================

:: Remove old Windows Service if it exists from a previous install
sc query PrintHubAgent >nul 2>&1
if %errorLevel% equ 0 (
    echo [INFO] Removing old Windows Service (replaced by Task Scheduler)...
    net stop PrintHubAgent >nul 2>&1
    timeout /t 2 /nobreak >nul
    "%VENV_PY%" agent_service.py remove >nul 2>&1
    timeout /t 2 /nobreak >nul
    echo [OK] Old service removed.
)

:: Remove existing scheduled task if it exists
schtasks /query /tn "PrintHubAgent" >nul 2>&1
if %errorLevel% equ 0 (
    echo [INFO] Removing existing scheduled task...
    schtasks /end /tn "PrintHubAgent" >nul 2>&1
    schtasks /delete /tn "PrintHubAgent" /f >nul 2>&1
)

:: Create Task Scheduler task - runs at login, as current user
echo [STEP 4] Creating Task Scheduler task (PrintHubAgent)...
schtasks /create /tn "PrintHubAgent" /tr "%INSTALL_DIR%\venv\Scripts\python.exe %INSTALL_DIR%\agent.py" /sc ONLOGON /rl HIGHEST /f
if %errorLevel% neq 0 (
    echo [ERROR] Failed to create scheduled task.
    pause & exit /b 1
)
echo [OK] Task Scheduler task created (runs at every login automatically).

:: Start the agent right now (don't wait for next login)
echo [STEP 5] Starting agent now...
schtasks /run /tn "PrintHubAgent"
if %errorLevel% neq 0 (
    echo [WARNING] Could not start task immediately. It will start at next login.
    echo           To start manually, run:
    echo             %VENV_PY% %INSTALL_DIR%\agent.py
) else (
    echo [OK] Agent started.
)

:: Wait a moment then check if Python process is running
timeout /t 5 /nobreak >nul
tasklist /fi "imagename eq python.exe" 2>nul | findstr "python.exe" >nul 2>&1
if %errorLevel% equ 0 (
    echo.
    echo ===========================================================
    echo  SUCCESS! PrintHub Agent is running.
    echo  It starts automatically every time you log into Windows.
    echo.
    echo  Installation folder: %INSTALL_DIR%
    echo  Log file: %INSTALL_DIR%\agent.log
    echo.
    echo  To stop the agent:
    echo    schtasks /end /tn "PrintHubAgent"
    echo.
    echo  To start the agent:
    echo    schtasks /run /tn "PrintHubAgent"
    echo.
    echo  To run in a visible window (for troubleshooting):
    echo    %VENV_PY% %INSTALL_DIR%\agent.py
    echo ===========================================================
) else (
    echo.
    echo [WARNING] Agent process not detected. Try running manually to see errors:
    echo   %VENV_PY% %INSTALL_DIR%\agent.py
    echo Or check the log at %INSTALL_DIR%\agent.log
)

echo.
pause
