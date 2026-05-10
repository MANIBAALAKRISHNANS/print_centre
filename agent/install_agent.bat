@echo off
:: PrintHub Agent - Windows Installer (Task Scheduler)
:: Run as Administrator
setlocal EnableDelayedExpansion
cd /d "%~dp0"

set LOG_FILE=%~dp0install_log.txt
echo PrintHub Agent Installer - %DATE% %TIME% > "%LOG_FILE%"

echo.
echo ===========================================================
echo  PrintHub Print Agent - Windows Installer
echo ===========================================================
echo.

:: Check Administrator privileges
:: fltmc is reliable on ALL Windows versions including Windows 11 Home
:: (net session fails on Windows 11 Home even when running as admin)
fltmc >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo [ERROR] This script must be run as Administrator.
    echo         Right-click the file and choose "Run as administrator"
    echo ERROR: Not running as Administrator >> "%LOG_FILE%"
    pause
    exit /b 1
)
echo [OK] Running as Administrator.
echo [OK] Running as Administrator >> "%LOG_FILE%"

:: Check Python
python --version >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo [ERROR] Python 3.11 is not installed or not in PATH.
    echo         Download from: https://www.python.org/downloads/
    echo         Make sure to tick "Add Python to PATH" when installing.
    echo ERROR: Python not found in PATH >> "%LOG_FILE%"
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo [OK] Python %PY_VER% found.
echo [OK] Python %PY_VER% >> "%LOG_FILE%"

set INSTALL_DIR=C:\PrintHubAgent

echo [STEP 1] Preparing installation directory %INSTALL_DIR%...
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

:: Copy all agent files to the install directory
echo [INFO] Copying agent files...
for %%f in (agent.py agent_service.py agent_config.py agent_setup.py requirements.txt) do (
    if exist "%~dp0%%f" (
        copy /y "%~dp0%%f" "%INSTALL_DIR%\%%f" >nul
        echo [INFO] Copied %%f >> "%LOG_FILE%"
    ) else (
        echo [WARNING] %%f not found in source folder - skipping
        echo WARNING: %%f not found >> "%LOG_FILE%"
    )
)
if exist "%~dp0agent_macos.py" copy /y "%~dp0agent_macos.py" "%INSTALL_DIR%\agent_macos.py" >nul
echo [OK] Agent files copied to %INSTALL_DIR%

cd /d "%INSTALL_DIR%"

set VENV_PY=%INSTALL_DIR%\venv\Scripts\python.exe

:: Create virtual environment
if not exist "venv\Scripts\python.exe" (
    echo [STEP 2] Creating virtual environment...
    echo [STEP 2] Creating venv >> "%LOG_FILE%"
    python -m venv venv
    if !ERRORLEVEL! neq 0 (
        echo [ERROR] Failed to create virtual environment.
        echo ERROR: venv creation failed >> "%LOG_FILE%"
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created.
) else (
    echo [OK] Virtual environment ready.
)

:: Install dependencies
echo [STEP 3] Installing dependencies (this may take 2-3 minutes)...
echo [STEP 3] Installing dependencies >> "%LOG_FILE%"
"%VENV_PY%" -m pip install --quiet --upgrade pip
"%VENV_PY%" -m pip install --quiet -r requirements.txt
if !ERRORLEVEL! neq 0 (
    echo [ERROR] Dependency installation failed. Check your internet connection.
    echo ERROR: pip install failed >> "%LOG_FILE%"
    pause
    exit /b 1
)
echo [OK] Dependencies installed.
echo [OK] Dependencies installed >> "%LOG_FILE%"

:: Run pywin32 post-install (required for win32print printer access)
echo [INFO] Running pywin32 post-install...
"%VENV_PY%" "%INSTALL_DIR%\venv\Scripts\pywin32_postinstall.py" -install
if !ERRORLEVEL! neq 0 (
    echo [WARNING] pywin32 post-install returned an error - printer access may not work
    echo WARNING: pywin32 post-install failed >> "%LOG_FILE%"
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
    echo [INFO] Running agent_setup.py --server !SERVER_URL! >> "%LOG_FILE%"
    "%VENV_PY%" agent_setup.py --code !ACT_CODE! --server !SERVER_URL! !NV_FLAG!
    if !ERRORLEVEL! neq 0 (
        echo [ERROR] Setup failed. Check the activation code and server URL.
        echo ERROR: agent_setup.py failed >> "%LOG_FILE%"
        pause
        exit /b 1
    )
    echo [OK] Configuration saved.
    echo [OK] Configuration saved >> "%LOG_FILE%"
) else (
    echo [OK] Existing configuration found - skipping setup.
)

:: Remove old Windows Service if it exists from a previous install
sc query PrintHubAgent >nul 2>&1
if !ERRORLEVEL! equ 0 (
    echo [INFO] Removing old Windows Service (replaced by Task Scheduler)...
    net stop PrintHubAgent >nul 2>&1
    timeout /t 2 /nobreak >nul
    "%VENV_PY%" agent_service.py remove >nul 2>&1
    timeout /t 2 /nobreak >nul
    echo [OK] Old service removed.
)

:: Create scheduled task via PowerShell (reliable on all Windows 11 editions)
echo [STEP 4] Creating Task Scheduler task (PrintHubAgent)...
echo [STEP 4] Creating scheduled task >> "%LOG_FILE%"

set PS1=%TEMP%\phtask_%RANDOM%.ps1
(
    echo Unregister-ScheduledTask -TaskName 'PrintHubAgent' -Confirm:$false -ErrorAction SilentlyContinue
    echo $a = New-ScheduledTaskAction -Execute '%INSTALL_DIR%\venv\Scripts\python.exe' -Argument '%INSTALL_DIR%\agent.py' -WorkingDirectory '%INSTALL_DIR%'
    echo $t = New-ScheduledTaskTrigger -AtLogOn
    echo $s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit 0 -StartWhenAvailable
    echo Register-ScheduledTask -TaskName 'PrintHubAgent' -Action $a -Trigger $t -Settings $s -RunLevel Highest -Force
) > "%PS1%"

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%"
if !ERRORLEVEL! neq 0 (
    echo [ERROR] Failed to create scheduled task.
    echo ERROR: Register-ScheduledTask failed >> "%LOG_FILE%"
    del "%PS1%" >nul 2>&1
    pause
    exit /b 1
)
del "%PS1%" >nul 2>&1
echo [OK] Task Scheduler task created (runs at every login automatically).
echo [OK] Scheduled task created >> "%LOG_FILE%"

:: Start the agent right now in a minimized window
echo [STEP 5] Starting agent now...
start "PrintHubAgent" /min "%INSTALL_DIR%\venv\Scripts\python.exe" "%INSTALL_DIR%\agent.py"
echo [OK] Agent started in background (minimized window in taskbar).
echo [OK] Agent started >> "%LOG_FILE%"

:: Wait then confirm agent is running
timeout /t 5 /nobreak >nul
tasklist /fi "imagename eq python.exe" 2>nul | findstr "python.exe" >nul 2>&1
if !ERRORLEVEL! equ 0 (
    echo.
    echo ===========================================================
    echo  SUCCESS! PrintHub Agent is running.
    echo  It starts automatically every time you log into Windows.
    echo.
    echo  Install folder : %INSTALL_DIR%
    echo  Log file       : %INSTALL_DIR%\agent.log
    echo  Install log    : %~dp0install_log.txt
    echo.
    echo  To stop the agent  : end task "python.exe" in Task Manager
    echo  To start manually  : %VENV_PY% %INSTALL_DIR%\agent.py
    echo ===========================================================
    echo SUCCESS >> "%LOG_FILE%"
) else (
    echo.
    echo [WARNING] Agent process not detected.
    echo           Try running manually to see errors:
    echo             %VENV_PY% %INSTALL_DIR%\agent.py
    echo           Or check the log: %INSTALL_DIR%\agent.log
    echo WARNING: agent not detected after start >> "%LOG_FILE%"
)

echo.
echo Install log saved to: %~dp0install_log.txt
echo.
pause
