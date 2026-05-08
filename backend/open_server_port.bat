@echo off
:: PrintHub Server Firewall Configurator
:: Run as Administrator to open Port 8000 for incoming Agent traffic

echo ---------------------------------------------------
echo PrintHub Server Firewall Configurator
echo ---------------------------------------------------

:: Check for Administrator privileges
net session >nul 2>&1
if %errorLevel% == 0 (
    echo [OK] Running with Administrator privileges.
) else (
    echo [ERROR] Please right-click this file and select "Run as Administrator".
    pause
    exit /b 1
)

echo [STEP 1] Opening Port 8000 for Incoming PrintHub Traffic...
netsh advfirewall firewall add rule name="PrintHub API Server" dir=in action=allow protocol=TCP localport=8000

echo [STEP 2] Verifying Rule...
netsh advfirewall firewall show rule name="PrintHub API Server"

echo ---------------------------------------------------
echo SUCCESS! Port 8000 is now open for your hospital network.
echo You can now turn your Windows Firewall back ON, and 
echo all laptops will still be able to connect!
echo ---------------------------------------------------
pause
