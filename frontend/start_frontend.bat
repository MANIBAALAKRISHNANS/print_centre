@echo off
title PrintHub Frontend
cd /d "%~dp0"
echo.
echo ===========================================================
echo  PrintHub Frontend (Dashboard)
echo  Local:   http://localhost:5173
echo  Network: http://192.168.1.14:5173
echo  Press Ctrl+C to stop
echo ===========================================================
echo.
npm run dev
pause
