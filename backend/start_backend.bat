@echo off
title PrintHub Backend
cd /d "%~dp0"
setlocal EnableDelayedExpansion

echo.
echo ===========================================================
echo  PrintHub Backend Server
echo ===========================================================
echo.

:: ── Auto-elevate to Admin (needed for firewall rules) ─────────
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [INFO] Requesting Administrator access for firewall setup...
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs -WorkingDirectory '%~dp0'"
    exit /b
)

:: ── Apply Firewall Rules ──────────────────────────────────────
echo [INFO] Applying firewall rules for LAN access...
netsh advfirewall firewall delete rule name="PrintHub Backend 8000" >nul 2>&1
netsh advfirewall firewall add rule name="PrintHub Backend 8000" dir=in action=allow protocol=TCP localport=8000 profile=any >nul 2>&1
netsh advfirewall firewall delete rule name="PrintHub Frontend 5173" >nul 2>&1
netsh advfirewall firewall add rule name="PrintHub Frontend 5173" dir=in action=allow protocol=TCP localport=5173 profile=any >nul 2>&1
echo [OK] Firewall rules applied (ports 8000 and 5173 open on all profiles).
echo.

echo  Local:   http://127.0.0.1:8000
echo  Network: http://0.0.0.0:8000
echo  Press Ctrl+C to stop
echo.

venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000 --timeout-keep-alive 75 --ws-ping-interval 20 --ws-ping-timeout 30
pause
