@echo off
:: PrintHub Agent — Windows Installer
:: Automatically re-launches itself in an elevated cmd /k window so the
:: window NEVER closes, even if an error occurs.
setlocal EnableDelayedExpansion

:: ── Self-elevation: if not already running elevated, relaunch with cmd /k ──
if /i not "%~1"=="ELEVATED" (
    powershell -NoProfile -Command ^
        "Start-Process cmd.exe -ArgumentList '/k \"%~dpnx0\" ELEVATED' -Verb RunAs"
    exit /b
)

cd /d "%~dp0"

set LOG=%~dp0install_log.txt
echo PrintHub Agent Installer  %DATE% %TIME% > "%LOG%"

echo.
echo ============================================================
echo   PrintHub Print Agent ^— Windows Installer
echo ============================================================
echo.

:: ── Admin check (fltmc works on all Windows versions / editions) ──────────
fltmc >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo [ERROR] Not running as Administrator.
    echo         Close this window, right-click install_agent.bat
    echo         and choose "Run as administrator".
    echo ERROR: Not admin >> "%LOG%"
    pause & exit /b 1
)
echo [OK] Running as Administrator.
echo [OK] Admin >> "%LOG%"

:: ── Python check ─────────────────────────────────────────────────────────
python --version >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo [ERROR] Python 3.11+ not found in PATH.
    echo         Download: https://www.python.org/downloads/
    echo         During install tick "Add Python to PATH".
    echo ERROR: Python not found >> "%LOG%"
    pause & exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo [OK] Python %PY_VER% found.
echo [OK] Python %PY_VER% >> "%LOG%"

:: ── Prepare install directory ─────────────────────────────────────────────
set INSTALL_DIR=C:\PrintHubAgent
echo [STEP 1] Preparing %INSTALL_DIR%...
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
echo [STEP 1] Install dir ready >> "%LOG%"

:: ── Copy agent files ──────────────────────────────────────────────────────
echo [INFO] Copying agent files...
for %%f in (agent.py agent_service.py agent_config.py agent_setup.py requirements.txt) do (
    if exist "%~dp0%%f" (
        copy /y "%~dp0%%f" "%INSTALL_DIR%\%%f" >nul
        echo [INFO] Copied %%f >> "%LOG%"
    ) else (
        echo [WARNING] %%f not found — skipping
        echo WARNING: %%f missing >> "%LOG%"
    )
)
if exist "%~dp0agent_macos.py" copy /y "%~dp0agent_macos.py" "%INSTALL_DIR%\agent_macos.py" >nul
echo [OK] Files copied to %INSTALL_DIR%
echo [OK] Files copied >> "%LOG%"

cd /d "%INSTALL_DIR%"
set VENV_PY=%INSTALL_DIR%\venv\Scripts\python.exe

:: ── Virtual environment ───────────────────────────────────────────────────
if not exist "venv\Scripts\python.exe" (
    echo [STEP 2] Creating virtual environment...
    echo [STEP 2] Creating venv >> "%LOG%"
    python -m venv venv
    if !ERRORLEVEL! neq 0 (
        echo [ERROR] Failed to create virtual environment.
        echo ERROR: venv creation failed >> "%LOG%"
        pause & exit /b 1
    )
    echo [OK] Virtual environment created.
    echo [OK] venv created >> "%LOG%"
) else (
    echo [OK] Virtual environment ready.
    echo [OK] venv already exists >> "%LOG%"
)

:: ── Bootstrap pip (Python 3.12+ may create venv without pip) ─────────────
echo [INFO] Bootstrapping pip into virtual environment...
echo [INFO] ensurepip starting >> "%LOG%"
"%VENV_PY%" -m ensurepip --upgrade >nul 2>&1
echo [OK] pip bootstrap done >> "%LOG%"

:: ── Install dependencies ──────────────────────────────────────────────────
echo [STEP 3] Installing dependencies...
echo [STEP 3] pip install starting >> "%LOG%"

"%VENV_PY%" -m pip install --upgrade pip
"%VENV_PY%" -m pip install -r requirements.txt
if !ERRORLEVEL! neq 0 (
    echo [ERROR] Dependency installation failed.
    echo         Check your internet connection and try again.
    echo ERROR: pip install failed >> "%LOG%"
    pause & exit /b 1
)
echo [OK] Dependencies installed.
echo [OK] pip install done >> "%LOG%"

:: ── First-time setup ──────────────────────────────────────────────────────
echo [STEP 4] Checking configuration...
echo [STEP 4] Checking config >> "%LOG%"

if not exist "agent_config.json" (
    echo.
    echo ============================================================
    echo   SETUP — Connect this PC to the PrintHub Server
    echo ============================================================
    echo.
    set /p SERVER_IP="  Server IP address (e.g. 192.168.1.14): "
    set /p SERVER_PORT="  Server port (press Enter for 8000): "
    if "!SERVER_PORT!"=="" set SERVER_PORT=8000

    set /p USE_HTTPS="  Use HTTPS? (y/N): "
    if /i "!USE_HTTPS!"=="y" (
        set PROTO=https
        set /p SKIP_TLS="  Skip TLS cert check for self-signed cert? (y/N): "
        if /i "!SKIP_TLS!"=="y" (set NV_FLAG=--no-verify) else (set NV_FLAG=)
    ) else (
        set PROTO=http
        set NV_FLAG=
    )
    set SERVER_URL=!PROTO!://!SERVER_IP!:!SERVER_PORT!

    echo.
    echo   Open PrintHub Dashboard ^> Agents ^> Generate Code
    set /p ACT_CODE="  Enter the 8-character activation code: "

    echo.
    echo   Connecting to !SERVER_URL!...
    echo [INFO] Running agent_setup.py --server !SERVER_URL! >> "%LOG%"
    "%VENV_PY%" agent_setup.py --code !ACT_CODE! --server !SERVER_URL! !NV_FLAG!
    if !ERRORLEVEL! neq 0 (
        echo [ERROR] Setup failed. Check the activation code and server URL.
        echo ERROR: agent_setup.py failed >> "%LOG%"
        pause & exit /b 1
    )
    echo [OK] Configuration saved.
    echo [OK] Config saved >> "%LOG%"
) else (
    echo [OK] Existing configuration found — skipping setup.
    echo [OK] Config already exists >> "%LOG%"
)

:: ── Remove old Windows Service if present ────────────────────────────────
sc query PrintHubAgent >nul 2>&1
if !ERRORLEVEL! equ 0 (
    echo [INFO] Removing old Windows Service...
    net stop PrintHubAgent >nul 2>&1
    timeout /t 2 /nobreak >nul
    "%VENV_PY%" agent_service.py remove >nul 2>&1
    timeout /t 2 /nobreak >nul
    echo [OK] Old service removed.
    echo [OK] Old service removed >> "%LOG%"
)

:: ── Create Task Scheduler entry via PowerShell ────────────────────────────
:: Write each line separately using >> to avoid (echo...) block parsing issues
echo [STEP 5] Creating Task Scheduler task...
echo [STEP 5] Creating scheduled task >> "%LOG%"

set PS1=%TEMP%\printhub_task.ps1

echo # PrintHub Agent Task > "%PS1%"
echo $task = Get-ScheduledTask -TaskName 'PrintHubAgent' -ErrorAction SilentlyContinue >> "%PS1%"
echo if ($task) { Unregister-ScheduledTask -TaskName 'PrintHubAgent' -Confirm:$false } >> "%PS1%"
echo $exe  = '%INSTALL_DIR%\venv\Scripts\python.exe' >> "%PS1%"
echo $arg  = '%INSTALL_DIR%\agent.py' >> "%PS1%"
echo $wdir = '%INSTALL_DIR%' >> "%PS1%"
echo $a = New-ScheduledTaskAction -Execute $exe -Argument $arg -WorkingDirectory $wdir >> "%PS1%"
echo $t = New-ScheduledTaskTrigger -AtLogOn >> "%PS1%"
echo $s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable >> "%PS1%"
echo Register-ScheduledTask -TaskName 'PrintHubAgent' -Action $a -Trigger $t -Settings $s -RunLevel Highest -Force >> "%PS1%"

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%"
if !ERRORLEVEL! neq 0 (
    echo [ERROR] Failed to create scheduled task.
    echo ERROR: Register-ScheduledTask failed >> "%LOG%"
    del "%PS1%" >nul 2>&1
    pause & exit /b 1
)
del "%PS1%" >nul 2>&1
echo [OK] Task Scheduler task created (auto-starts at every login).
echo [OK] Scheduled task created >> "%LOG%"

:: ── Start the agent now ───────────────────────────────────────────────────
echo [STEP 6] Starting agent now...
start "PrintHubAgent" /min "%VENV_PY%" "%INSTALL_DIR%\agent.py"
echo [OK] Agent started in background.
echo [OK] Agent started >> "%LOG%"

timeout /t 5 /nobreak >nul

tasklist /fi "imagename eq python.exe" 2>nul | findstr /i "python.exe" >nul 2>&1
if !ERRORLEVEL! equ 0 (
    echo.
    echo ============================================================
    echo   SUCCESS! PrintHub Agent is installed and running.
    echo   It will start automatically every time you log in.
    echo.
    echo   Install folder : %INSTALL_DIR%
    echo   Agent log      : %INSTALL_DIR%\agent.log
    echo   Install log    : %~dp0install_log.txt
    echo ============================================================
    echo SUCCESS >> "%LOG%"
) else (
    echo.
    echo [WARNING] Agent process not detected after start.
    echo           Run manually to see errors:
    echo             %VENV_PY% %INSTALL_DIR%\agent.py
    echo           Or check: %INSTALL_DIR%\agent.log
    echo WARNING: agent not detected >> "%LOG%"
)

echo.
echo Install log: %~dp0install_log.txt
echo.
pause
