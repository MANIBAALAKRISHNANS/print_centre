@echo off
title PrintHub Backend
cd /d "%~dp0"
echo.
echo ===========================================================
echo  PrintHub Backend Server
echo  Local:   http://127.0.0.1:8000
echo  Network: http://192.168.1.14:8000
echo  Press Ctrl+C to stop
echo ===========================================================
echo.
venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000
pause
