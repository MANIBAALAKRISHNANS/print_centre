@echo off
title PrintHub Frontend
cd /d "%~dp0"
setlocal EnableDelayedExpansion

echo.
echo ===========================================================
echo  PrintHub Frontend (Dashboard)
echo ===========================================================
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

echo [OK] Serving production build on port 5173
echo.
echo  Dashboard (this PC)  : http://localhost:5173
echo  Dashboard (network)  : http://%SERVER_IP%:5173
echo.
echo  This is a stable production server.
echo  Press Ctrl+C to stop.
echo.

npx serve -s dist -l 5173
pause
