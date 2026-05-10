@echo off
title PrintHub Frontend
cd /d "%~dp0"
setlocal EnableDelayedExpansion

echo.
echo ===========================================================
echo  PrintHub Frontend (Dashboard)
echo ===========================================================
echo.

:: ── Auto-elevate to Admin (required for firewall rules) ────────
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [INFO] Requesting Administrator access for firewall setup...
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs -WorkingDirectory '%~dp0'"
    exit /b
)

:: ── Find Python ────────────────────────────────────────────────
set PYTHON_EXE=
for /f "tokens=*" %%i in ('where python 2^>nul') do (
    if "!PYTHON_EXE!"=="" set PYTHON_EXE=%%i
)
if "!PYTHON_EXE!"=="" (
    for /f "tokens=*" %%i in ('where python3 2^>nul') do (
        if "!PYTHON_EXE!"=="" set PYTHON_EXE=%%i
    )
)
if "!PYTHON_EXE!"=="" (
    echo [ERROR] Python not found. Install Python 3.11+ and add it to PATH.
    pause
    exit /b 1
)
echo [INFO] Python: !PYTHON_EXE!

:: ── Firewall Step 1: Remove ALL rules tied to this python.exe ──
:: Windows auto-adds a BLOCK rule when the user dismisses the
:: "Allow Python through Firewall?" security popup.
:: That program-level block overrides all port-based allow rules.
:: Deleting it first ensures our allow rules actually take effect.
echo [INFO] Removing any existing Python firewall rules (including auto-blocks)...
netsh advfirewall firewall delete rule name=all program="!PYTHON_EXE!" >nul 2>&1

:: ── Firewall Step 2: Add program-level ALLOW for python.exe ────
:: Program-level rules take priority over port-level rules.
netsh advfirewall firewall add rule ^
    name="PrintHub Python Allow" ^
    dir=in action=allow ^
    program="!PYTHON_EXE!" ^
    enable=yes profile=any >nul 2>&1
echo [OK] Program-level ALLOW rule added for python.exe

:: ── Firewall Step 3: Add port-level ALLOW rules as backup ──────
netsh advfirewall firewall delete rule name="PrintHub Frontend 5173" >nul 2>&1
netsh advfirewall firewall add rule name="PrintHub Frontend 5173" dir=in action=allow protocol=TCP localport=5173 profile=any >nul 2>&1
netsh advfirewall firewall delete rule name="PrintHub Backend 8000" >nul 2>&1
netsh advfirewall firewall add rule name="PrintHub Backend 8000" dir=in action=allow protocol=TCP localport=8000 profile=any >nul 2>&1
echo [OK] Port-level ALLOW rules added (5173 and 8000)

:: ── Firewall Step 4: PowerShell New-NetFirewallRule (Win10/11) ─
powershell -NonInteractive -Command "$e='SilentlyContinue'; Get-NetFirewallRule -DisplayName 'PrintHub*' -EA $e | Remove-NetFirewallRule -EA $e; New-NetFirewallRule -DisplayName 'PrintHub Frontend 5173' -Direction Inbound -Protocol TCP -LocalPort 5173 -Action Allow -Profile Any -EA $e | Out-Null; New-NetFirewallRule -DisplayName 'PrintHub Backend 8000' -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Any -EA $e | Out-Null" >nul 2>&1
echo [OK] PowerShell firewall rules applied (all profiles)
echo.

:: ── Check if production build exists ───────────────────────────
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

echo [OK] Starting server...
echo.

:: ── Start Python SPA server (blocks — keep this window open) ───
"!PYTHON_EXE!" serve_spa.py
pause
