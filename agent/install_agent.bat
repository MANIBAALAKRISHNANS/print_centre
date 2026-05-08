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

:: Check if registered
if not exist "agent_config.json" (
    echo ---------------------------------------------------
    echo WARNING: Agent is not yet registered!
    echo Please run the following command first:
    echo python agent_setup.py --code YOUR_CODE --server http://YOUR_SERVER_IP:8000
    echo ---------------------------------------------------
    pause
    exit /b 1
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
