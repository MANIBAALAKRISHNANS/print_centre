@echo off
title PrintHub Frontend - Rebuild
cd /d "%~dp0"
setlocal EnableDelayedExpansion

echo.
echo ===========================================================
echo  PrintHub Frontend - Rebuild Production Bundle
echo  Run this whenever you change the server IP in .env
echo ===========================================================
echo.

:: ── Show current VITE_API_URL ─────────────────────────────────
for /f "delims=" %%a in ('findstr /i "VITE_API_URL" .env 2^>nul') do set CURRENT_URL=%%a
echo [INFO] Current setting: !CURRENT_URL!
echo.
echo [INFO] If the server IP is wrong, close this window, edit
echo        frontend\.env and change VITE_API_URL, then run this again.
echo.
pause

:: ── Delete old build ─────────────────────────────────────────
if exist "dist" (
    echo [INFO] Removing old build...
    rmdir /s /q dist
)

:: ── Build ─────────────────────────────────────────────────────
echo [INFO] Building... (this takes 30-60 seconds)
echo.
call npm run build
if !ERRORLEVEL! neq 0 (
    echo.
    echo [ERROR] Build failed. Check the errors above.
    pause
    exit /b 1
)

echo.
echo ===========================================================
echo  Build complete!
echo  Now run start_frontend.bat to start the dashboard.
echo ===========================================================
echo.
pause
