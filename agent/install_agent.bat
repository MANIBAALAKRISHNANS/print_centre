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

:: ============================================================
:: IMPORTANT: Install to C:\PrintHubAgent - NOT to OneDrive.
:: Windows Services run as SYSTEM, which cannot access files
:: in a user's OneDrive folder. All agent files and the venv
:: must live in a path SYSTEM can read.
:: ============================================================
set INSTALL_DIR=C:\PrintHubAgent

echo [STEP 1] Preparing installation directory %INSTALL_DIR%...
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

:: Copy all agent files from the source folder to the install dir
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

:: Switch all remaining work to the install directory
cd /d "%INSTALL_DIR%"

:: Create virtual environment inside INSTALL_DIR (not OneDrive)
if not exist "venv\Scripts\python.exe" (
    echo [STEP 2] Creating virtual environment in %INSTALL_DIR%\venv...
    python -m venv venv
    if %errorLevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause & exit /b 1
    )
    echo [OK] Virtual environment created.
) else (
    echo [OK] Virtual environment ready.
)

set VENV_PY=%INSTALL_DIR%\venv\Scripts\python.exe

:: Install dependencies
echo [STEP 3] Installing dependencies...
"%VENV_PY%" -m pip install --quiet --upgrade pip
"%VENV_PY%" -m pip install --quiet -r requirements.txt
if %errorLevel% neq 0 (
    echo [ERROR] Dependency installation failed. Check internet connection.
    pause & exit /b 1
)
echo [OK] Dependencies installed.

:: Run pywin32 post-install (always - required for Windows Service DLL registration)
echo [INFO] Running pywin32 post-install...
for /f "delims=" %%i in ('"%VENV_PY%" -c "import sys; print(sys.prefix)"') do set VENV_PREFIX=%%i
"%VENV_PY%" "!VENV_PREFIX!\Scripts\pywin32_postinstall.py" -install >nul 2>&1
echo [OK] pywin32 post-install complete.

:: First-time setup (only if no config exists in install dir)
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

:: Grant SYSTEM full access to the install directory and config file
:: NOTE: icacls with (OI)(CI) flags MUST be outside any parenthesized if block
:: to avoid a batch parser bug with parentheses in arguments.
echo [INFO] Setting SYSTEM permissions on %INSTALL_DIR%...
icacls "%INSTALL_DIR%" /grant:r "SYSTEM:(OI)(CI)F" >nul 2>&1
echo [OK] SYSTEM permissions set.

:: Stop and remove existing service if it exists
sc query PrintHubAgent >nul 2>&1
if %errorLevel% equ 0 (
    echo [STEP 4] Removing existing service...
    net stop PrintHubAgent >nul 2>&1
    timeout /t 3 /nobreak >nul
    "%VENV_PY%" agent_service.py remove >nul 2>&1
    timeout /t 2 /nobreak >nul
)

:: Install Windows Service (registers pythonservice.exe from the venv in INSTALL_DIR)
echo [STEP 4] Installing Windows Service (PrintHubAgent)...
"%VENV_PY%" agent_service.py --startup auto install
if %errorLevel% neq 0 (
    echo [ERROR] Service installation failed.
    pause & exit /b 1
)
echo [OK] Service installed.

:: Start the service using net start (returns proper exit code unlike agent_service.py start)
echo [STEP 5] Starting service...
net start PrintHubAgent
if %errorLevel% neq 0 (
    echo [WARNING] Service did not start. Check Event Viewer or:
    echo           %INSTALL_DIR%\agent_service.log
    echo           %INSTALL_DIR%\agent.log
) else (
    echo [OK] Service started.
)

:: Verify after a short wait
timeout /t 4 /nobreak >nul
sc query PrintHubAgent | findstr "RUNNING" >nul 2>&1
if %errorLevel% equ 0 (
    echo.
    echo ===========================================================
    echo  SUCCESS! PrintHub Agent is running as a Windows Service.
    echo  It starts automatically on every boot.
    echo.
    echo  Installation: %INSTALL_DIR%
    echo  Logs:
    echo    %INSTALL_DIR%\agent.log
    echo    %INSTALL_DIR%\agent_service.log
    echo.
    echo  Commands (run as Administrator from %INSTALL_DIR%):
    echo    net stop PrintHubAgent
    echo    net start PrintHubAgent
    echo    venv\Scripts\python.exe agent_service.py remove
    echo    venv\Scripts\python.exe agent_setup.py --status
    echo ===========================================================
) else (
    echo.
    echo [WARNING] Service is not in RUNNING state.
    echo Run this to see the Python error directly:
    echo   %VENV_PY% agent.py
    echo Or check logs at %INSTALL_DIR%\
)

echo.
pause
