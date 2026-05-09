@echo off
:: ═══════════════════════════════════════════════════════════════
:: PrintHub Agent — Windows Service Installer
:: Run as Administrator
:: ═══════════════════════════════════════════════════════════════
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo ═══════════════════════════════════════════════════════════
echo  PrintHub Print Agent — Windows Installer
echo ═══════════════════════════════════════════════════════════
echo.

:: ── Check Administrator privileges ──────────────────────────────
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] This script must be run as Administrator.
    echo         Right-click ^> "Run as administrator"
    pause & exit /b 1
)
echo [OK] Running as Administrator.

:: ── Check Python ─────────────────────────────────────────────────
python --version >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] Python 3.11+ is not installed or not in PATH.
    echo         Download: https://www.python.org/downloads/
    pause & exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo [OK] Python %PY_VER% found.

:: ── Virtual environment ─────────────────────────────────────────
if not exist "venv\" (
    echo [STEP 1] Creating virtual environment...
    python -m venv venv
    if %errorLevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause & exit /b 1
    )
)
echo [OK] Virtual environment ready.

:: ── Activate and install dependencies ───────────────────────────
echo [STEP 2] Installing dependencies...
call "venv\Scripts\activate.bat"
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
if %errorLevel% neq 0 (
    echo [ERROR] Dependency installation failed. Check internet connection.
    pause & exit /b 1
)
echo [OK] Dependencies installed (including websocket-client for real-time).

:: ── First-time setup ────────────────────────────────────────────
if not exist "agent_config.json" (
    echo.
    echo ═══════════════════════════════════════════════════════════
    echo  SETUP — Connect this workstation to PrintHub Server
    echo ═══════════════════════════════════════════════════════════
    echo.
    set /p SERVER_IP="  Server IP address (e.g. 192.168.1.50): "
    set /p SERVER_PORT="  Server port [8000]: "
    if "!SERVER_PORT!"=="" set SERVER_PORT=8000

    set /p USE_HTTPS="  Use HTTPS? (y/N): "
    if /i "!USE_HTTPS!"=="y" (
        set PROTO=https
    ) else (
        set PROTO=http
    )
    set SERVER_URL=!PROTO!://!SERVER_IP!:!SERVER_PORT!

    echo.
    echo  Open the PrintHub dashboard ^> Agents ^> Generate Code
    set /p ACT_CODE="  Enter the 8-character activation code: "

    set /p NO_VERIFY=""
    if /i "!USE_HTTPS!"=="y" (
        set /p SKIP_VERIFY="  Skip TLS certificate verification? (for self-signed certs) (y/N): "
        if /i "!SKIP_VERIFY!"=="y" (
            set NV_FLAG=--no-verify
        ) else (
            set NV_FLAG=
        )
    ) else (
        set NV_FLAG=
    )

    echo.
    echo  Saving activation code for !SERVER_URL!...
    python agent_setup.py --code !ACT_CODE! --server !SERVER_URL! !NV_FLAG!
    if %errorLevel% neq 0 (
        echo [ERROR] Setup failed. Check the activation code and server URL.
        pause & exit /b 1
    )
) else (
    echo [OK] Existing configuration found — skipping setup.
)

:: ── Stop existing service if running ────────────────────────────
sc query PrintHubAgent >nul 2>&1
if %errorLevel% equ 0 (
    echo [STEP 3] Stopping existing service...
    python agent_service.py stop >nul 2>&1
    python agent_service.py remove >nul 2>&1
    timeout /t 2 /nobreak >nul
)

:: ── Install Windows Service ──────────────────────────────────────
echo [STEP 3] Installing Windows Service (PrintHubAgent)...
python agent_service.py --startup auto install
if %errorLevel% neq 0 (
    echo [ERROR] Service installation failed.
    echo         Ensure pywin32 is installed: pip install pywin32
    pause & exit /b 1
)
echo [OK] Service installed.

:: ── Start the service ───────────────────────────────────────────
echo [STEP 4] Starting service...
python agent_service.py start
if %errorLevel% neq 0 (
    echo [WARNING] Service start returned non-zero. Check Event Viewer or:
    echo           type C:\PrintHubAgent\agent_service.log
) else (
    echo [OK] Service started.
)

:: ── Verify ──────────────────────────────────────────────────────
timeout /t 3 /nobreak >nul
sc query PrintHubAgent | findstr "RUNNING" >nul 2>&1
if %errorLevel% equ 0 (
    echo.
    echo ═══════════════════════════════════════════════════════════
    echo  SUCCESS! PrintHub Agent is running as a Windows Service.
    echo  It will start automatically on every boot.
    echo.
    echo  Logs : C:\PrintHubAgent\agent.log
    echo         C:\PrintHubAgent\agent_service.log
    echo.
    echo  Commands:
    echo    Stop    - python agent_service.py stop
    echo    Start   - python agent_service.py start
    echo    Restart - python agent_service.py restart
    echo    Remove  - python agent_service.py remove
    echo    Status  - python agent_setup.py --status
    echo ═══════════════════════════════════════════════════════════
) else (
    echo.
    echo [WARNING] Service may not have started correctly.
    echo Check: C:\PrintHubAgent\agent_service.log
)

echo.
pause
