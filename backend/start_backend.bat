@echo off
title PrintHub Backend
cd /d "%~dp0"
setlocal EnableDelayedExpansion

echo.
echo ===========================================================
echo  PrintHub Backend Server
echo ===========================================================
echo.

:: ── Auto-elevate to Admin (required for firewall rules) ────────
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [INFO] Requesting Administrator access for firewall setup...
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs -WorkingDirectory '%~dp0'"
    exit /b
)

:: ── Find the venv Python ───────────────────────────────────────
set VENV_PYTHON=%~dp0venv\Scripts\python.exe
if not exist "!VENV_PYTHON!" (
    echo [ERROR] venv not found at %~dp0venv\Scripts\python.exe
    echo [INFO]  Run: python -m venv venv  then  venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)
echo [INFO] Python: !VENV_PYTHON!

:: ── Firewall Step 1: Remove ALL rules tied to this python.exe ──
:: Windows auto-adds a BLOCK rule when the user dismisses the
:: "Allow Python through Firewall?" security popup.
:: That program-level block overrides all port-based allow rules.
echo [INFO] Removing any existing Python firewall rules (including auto-blocks)...
netsh advfirewall firewall delete rule name=all program="!VENV_PYTHON!" >nul 2>&1

:: Also clear the system Python if present (covers serve_spa.py too)
set SYS_PYTHON=
for /f "tokens=*" %%i in ('where python 2^>nul') do (
    if "!SYS_PYTHON!"=="" set SYS_PYTHON=%%i
)
if not "!SYS_PYTHON!"=="" (
    netsh advfirewall firewall delete rule name=all program="!SYS_PYTHON!" >nul 2>&1
    netsh advfirewall firewall add rule name="PrintHub Python Allow" dir=in action=allow program="!SYS_PYTHON!" enable=yes profile=any >nul 2>&1
)

:: ── Firewall Step 2: Add program-level ALLOW for venv python ───
netsh advfirewall firewall add rule ^
    name="PrintHub Venv Python Allow" ^
    dir=in action=allow ^
    program="!VENV_PYTHON!" ^
    enable=yes profile=any >nul 2>&1
echo [OK] Program-level ALLOW rule added for python.exe

:: ── Firewall Step 3: Add port-level ALLOW rules as backup ──────
netsh advfirewall firewall delete rule name="PrintHub Backend 8000" >nul 2>&1
netsh advfirewall firewall add rule name="PrintHub Backend 8000" dir=in action=allow protocol=TCP localport=8000 profile=any >nul 2>&1
netsh advfirewall firewall delete rule name="PrintHub Frontend 5173" >nul 2>&1
netsh advfirewall firewall add rule name="PrintHub Frontend 5173" dir=in action=allow protocol=TCP localport=5173 profile=any >nul 2>&1
echo [OK] Port-level ALLOW rules added (8000 and 5173)

:: ── Firewall Step 4: PowerShell New-NetFirewallRule (Win10/11) ─
powershell -NonInteractive -Command "$e='SilentlyContinue'; Get-NetFirewallRule -DisplayName 'PrintHub*' -EA $e | Remove-NetFirewallRule -EA $e; New-NetFirewallRule -DisplayName 'PrintHub Backend 8000' -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Any -EA $e | Out-Null; New-NetFirewallRule -DisplayName 'PrintHub Frontend 5173' -Direction Inbound -Protocol TCP -LocalPort 5173 -Action Allow -Profile Any -EA $e | Out-Null" >nul 2>&1
echo [OK] PowerShell firewall rules applied (all profiles)
echo.

echo  Local:   http://127.0.0.1:8000
echo  Network: http://0.0.0.0:8000
echo  Press Ctrl+C to stop
echo.

:: ── Start backend (blocks — keep this window open) ─────────────
"!VENV_PYTHON!" -m uvicorn main:app --host 0.0.0.0 --port 8000 --timeout-keep-alive 75 --ws-ping-interval 20 --ws-ping-timeout 30
pause
