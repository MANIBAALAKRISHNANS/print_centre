#!/bin/bash

# PrintHub Agent macOS Installer
# Installs the agent as a background LaunchAgent

echo "---------------------------------------------------"
echo "PrintHub Agent macOS Installer"
echo "---------------------------------------------------"

# Ensure we are in the agent directory
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# 1. Setup Virtual Environment
if [ ! -d "venv" ]; then
    echo "[STEP 1] Creating virtual environment..."
    python3 -m venv venv
fi

# 2. Install Dependencies
echo "[STEP 2] Installing dependencies..."
source venv/bin/activate
pip install -r requirements.txt

# Ask for Server and Code if not already registered
if [ ! -f "agent_config.json" ]; then
    echo "---------------------------------------------------"
    echo "SETUP: Connecting to your PrintHub Server"
    echo "---------------------------------------------------"
    read -p "Enter Server IP (e.g. 192.168.1.50): " SERVER_IP
    read -p "Enter Activation Code from Dashboard: " ACT_CODE
    
    echo "Registering with server http://$SERVER_IP:8000..."
    python3 agent_setup.py --code "$ACT_CODE" --server "http://$SERVER_IP:8000"
fi

# 3. Create LaunchAgent Plist
PLIST_PATH="$HOME/Library/LaunchAgents/com.printhub.agent.plist"
echo "[STEP 3] Configuring background service..."

cat <<EOF > "$PLIST_PATH"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.printhub.agent</string>
    <key>ProgramArguments</key>
    <array>
        <string>$DIR/venv/bin/python3</string>
        <string>$DIR/agent.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>WorkingDirectory</key>
    <string>$DIR</string>
    <key>StandardOutPath</key>
    <string>$HOME/Library/Logs/printhub_agent.log</string>
    <key>StandardErrorPath</key>
    <string>$HOME/Library/Logs/printhub_agent_error.log</string>
</dict>
</plist>
EOF

# 4. Load the Service
echo "[STEP 4] Starting the service..."
launchctl unload "$PLIST_PATH" 2>/dev/null
launchctl load "$PLIST_PATH"

echo "---------------------------------------------------"
echo "SUCCESS! The PrintHub Agent is now running in the"
echo "background. It will start automatically when you login."
echo "---------------------------------------------------"
echo "Logs can be found at: ~/Library/Logs/printhub_agent.log"
