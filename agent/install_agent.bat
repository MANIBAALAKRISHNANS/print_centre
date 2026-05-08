@echo off
:: PrintHub Agent Service Installer
:: Must be run as Administrator

echo ---------------------------------------------------
echo PrintHub Agent Service Installer
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

:: Ensure venv exists
if not exist "venv" (
    echo [STEP 1] Creating virtual environment...
    python -m venv venv
)

:: Activate and Install Dependencies
echo [STEP 2] Installing dependencies...
call .\venv\Scripts\activate
pip install -r requirements.txt

:: Ask for Server and Code if not already registered
if not exist "agent_config.json" (
    echo ---------------------------------------------------
    echo SETUP: Connecting to your PrintHub Server
    echo ---------------------------------------------------
    set /p SERVER_IP="Enter Server IP (e.g. 192.168.1.50): "
    set /p ACT_CODE="Enter Activation Code from Dashboard: "
    
    echo Registering with server http://%SERVER_IP%:8000...
    python agent_setup.py --code %ACT_CODE% --server http://%SERVER_IP%:8000
)

:: Install the Service
echo [STEP 3] Installing Windows Service...
python agent_service.py --startup auto install

:: Start the Service
echo [STEP 4] Starting the service...
python agent_service.py start

echo ---------------------------------------------------
echo SUCCESS! The PrintHub Agent is now running as a 
echo background service. It will start automatically 
echo whenever this computer turns on.
echo ---------------------------------------------------
pause
