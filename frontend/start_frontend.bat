@echo off
title PrintHub Frontend
cd /d "%~dp0"
setlocal EnableDelayedExpansion

echo.
echo ===========================================================
echo  PrintHub Frontend (Dashboard)
echo ===========================================================
echo.

:: ── Auto-elevate to Admin (needed for firewall rules) ─────────
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [INFO] Requesting Administrator access for firewall setup...
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs -WorkingDirectory '%~dp0'"
    exit /b
)

:: ── Apply Firewall Rules (always refresh to ensure correct profile) ─
echo [INFO] Applying firewall rules for LAN access...
netsh advfirewall firewall delete rule name="PrintHub Frontend 5173" >nul 2>&1
netsh advfirewall firewall add rule name="PrintHub Frontend 5173" dir=in action=allow protocol=TCP localport=5173 profile=any >nul 2>&1
netsh advfirewall firewall delete rule name="PrintHub Backend 8000" >nul 2>&1
netsh advfirewall firewall add rule name="PrintHub Backend 8000" dir=in action=allow protocol=TCP localport=8000 profile=any >nul 2>&1
echo [OK] Firewall rules applied (ports 5173 and 8000 open on all profiles).
echo.

:: ── Check if production build exists ─────────────────────────
if not exist "dist\index.html" (
    echo [INFO] No production build found. Building now...
    echo [INFO] This takes about 30-60 seconds. Please wait...
    echo.
    call npm run build
    if !ERRORLEVEL! neq 0 (
        echo.
        echo [ERROR] Build failed. Check the errors above.
        echo [INFO]  Make sure you ran: npm install
        echo [INFO]  And that frontend\.env has the correct VITE_API_URL
        pause
        exit /b 1
    )
    echo.
    echo [OK] Build complete.
)

:: ── Get server IP from .env ───────────────────────────────────
set SERVER_IP=YOUR_SERVER_IP
for /f "tokens=2 delims=/" %%a in ('findstr /i "VITE_API_URL" .env 2^>nul') do (
    for /f "tokens=1 delims=:" %%b in ("%%a") do set SERVER_IP=%%b
)

echo [OK] Serving production build on ALL network interfaces, port 5173
echo.
echo  Dashboard (this PC)  : http://localhost:5173
echo  Dashboard (network)  : http://%SERVER_IP%:5173
echo.
echo  This is a stable production server.
echo  Press Ctrl+C to stop.
echo.

:: ── Start server bound to ALL interfaces (0.0.0.0) ───────────
npx serve -s dist -l tcp://0.0.0.0:5173
pause
