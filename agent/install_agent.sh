#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# PrintHub Agent — macOS / Linux Installer
# ═══════════════════════════════════════════════════════════════
# NOTE: Do NOT use set -e here — it causes silent exits when any
# command returns non-zero (e.g. grep finding no match, pip warnings).
# Each critical step has explicit error handling instead.

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

OS="$(uname -s)"
PLIST_PATH="$HOME/Library/LaunchAgents/com.printhub.agent.plist"
LOG_DIR="$HOME/Library/Logs/PrintHubAgent"
LOG_FILE="$DIR/install_log.txt"

echo "" | tee "$LOG_FILE"
echo "═══════════════════════════════════════════════════════════" | tee -a "$LOG_FILE"
echo " PrintHub Print Agent — Installer" | tee -a "$LOG_FILE"
echo "═══════════════════════════════════════════════════════════" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# ── Check Python ─────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "[ERROR] Python 3 not found." | tee -a "$LOG_FILE"
    echo "        macOS: brew install python" | tee -a "$LOG_FILE"
    echo "        Ubuntu: sudo apt install python3 python3-venv" | tee -a "$LOG_FILE"
    echo "Press Enter to close..."
    read -r
    exit 1
fi
PY_VER="$(python3 --version 2>&1)"
echo "[OK] $PY_VER" | tee -a "$LOG_FILE"

# ── Create log directory ─────────────────────────────────────────
mkdir -p "$LOG_DIR"
chmod 700 "$LOG_DIR"
echo "[OK] Log directory: $LOG_DIR" | tee -a "$LOG_FILE"

# ── Virtual environment ─────────────────────────────────────────
if [ ! -d "$DIR/venv" ]; then
    echo "[STEP 1] Creating virtual environment..." | tee -a "$LOG_FILE"
    python3 -m venv "$DIR/venv"
    if [ $? -ne 0 ]; then
        echo "[ERROR] Failed to create virtual environment." | tee -a "$LOG_FILE"
        echo "        Make sure python3-venv is installed:" | tee -a "$LOG_FILE"
        echo "        Ubuntu: sudo apt install python3-venv" | tee -a "$LOG_FILE"
        echo "Press Enter to close..."
        read -r
        exit 1
    fi
    echo "[OK] Virtual environment created." | tee -a "$LOG_FILE"
else
    echo "[OK] Virtual environment already exists." | tee -a "$LOG_FILE"
fi

VENV_PY="$DIR/venv/bin/python3"
VENV_PIP="$DIR/venv/bin/pip"

# ── Install dependencies ─────────────────────────────────────────
echo "[STEP 2] Installing dependencies..." | tee -a "$LOG_FILE"
"$VENV_PIP" install --upgrade pip
if [ $? -ne 0 ]; then
    echo "[WARNING] pip upgrade failed — continuing anyway." | tee -a "$LOG_FILE"
fi

"$VENV_PIP" install -r "$DIR/requirements.txt"
if [ $? -ne 0 ]; then
    echo "[ERROR] Dependency installation failed." | tee -a "$LOG_FILE"
    echo "        Check your internet connection and try again." | tee -a "$LOG_FILE"
    echo "Press Enter to close..."
    read -r
    exit 1
fi
echo "[OK] Dependencies installed." | tee -a "$LOG_FILE"

# ── First-time setup ────────────────────────────────────────────
echo "[STEP 3] Checking configuration..." | tee -a "$LOG_FILE"
if [ ! -f "$DIR/agent_config.json" ]; then
    echo "" | tee -a "$LOG_FILE"
    echo "═══════════════════════════════════════════════════════════"
    echo " SETUP — Connect this workstation to PrintHub Server"
    echo "═══════════════════════════════════════════════════════════"
    echo ""
    read -rp "  Server IP address (e.g. 192.168.1.14): " SERVER_IP
    read -rp "  Server port (press Enter for 8000): " SERVER_PORT
    SERVER_PORT="${SERVER_PORT:-8000}"

    read -rp "  Use HTTPS? (y/N): " USE_HTTPS
    if [[ "${USE_HTTPS,,}" == "y" ]]; then
        PROTO="https"
        read -rp "  Skip TLS certificate verification for self-signed cert? (y/N): " SKIP_TLS
        if [[ "${SKIP_TLS,,}" == "y" ]]; then
            NV_FLAG="--no-verify"
        else
            NV_FLAG=""
        fi
    else
        PROTO="http"
        NV_FLAG=""
    fi
    SERVER_URL="${PROTO}://${SERVER_IP}:${SERVER_PORT}"

    echo ""
    echo "  Open the PrintHub Dashboard > Agents > Generate Code"
    read -rp "  Enter the 8-character activation code: " ACT_CODE

    echo ""
    echo "  Connecting to $SERVER_URL..." | tee -a "$LOG_FILE"
    echo "[INFO] Running agent_setup.py --server $SERVER_URL" >> "$LOG_FILE"
    "$VENV_PY" "$DIR/agent_setup.py" --code "$ACT_CODE" --server "$SERVER_URL" $NV_FLAG
    if [ $? -ne 0 ]; then
        echo "[ERROR] Setup failed. Check the activation code and server URL." | tee -a "$LOG_FILE"
        echo "Press Enter to close..."
        read -r
        exit 1
    fi
    echo "[OK] Configuration saved." | tee -a "$LOG_FILE"
else
    echo "[OK] Existing configuration found — skipping setup." | tee -a "$LOG_FILE"
fi

# ── macOS launchd service ────────────────────────────────────────
if [ "$OS" = "Darwin" ]; then
    echo "[STEP 4] Setting up launchd auto-start service..." | tee -a "$LOG_FILE"

    # Unload any existing instance (ignore errors — it may not be loaded)
    if launchctl list 2>/dev/null | grep -q "com.printhub.agent"; then
        echo "[INFO] Removing existing launchd service..." | tee -a "$LOG_FILE"
        launchctl unload "$PLIST_PATH" 2>/dev/null || true
    fi

    mkdir -p "$(dirname "$PLIST_PATH")"

    cat >"$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.printhub.agent</string>
    <key>ProgramArguments</key>
    <array>
        <string>${DIR}/venv/bin/python3</string>
        <string>${DIR}/agent.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>WorkingDirectory</key>
    <string>${DIR}</string>
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/agent.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/agent_error.log</string>
    <key>ThrottleInterval</key>
    <integer>10</integer>
</dict>
</plist>
EOF

    if [ $? -ne 0 ]; then
        echo "[ERROR] Failed to write launchd plist file." | tee -a "$LOG_FILE"
        echo "Press Enter to close..."
        read -r
        exit 1
    fi

    chmod 644 "$PLIST_PATH"
    echo "[STEP 5] Starting agent now..." | tee -a "$LOG_FILE"
    launchctl load "$PLIST_PATH"
    if [ $? -ne 0 ]; then
        echo "[WARNING] launchctl load returned an error." | tee -a "$LOG_FILE"
        echo "          Try starting manually: $VENV_PY $DIR/agent.py" | tee -a "$LOG_FILE"
    fi

    sleep 2
    if launchctl list 2>/dev/null | grep -q "com.printhub.agent"; then
        echo "" | tee -a "$LOG_FILE"
        echo "═══════════════════════════════════════════════════════════"
        echo " SUCCESS! PrintHub Agent is installed and running."
        echo " It starts automatically at every login."
        echo ""
        echo " Install folder : $DIR"
        echo " Agent log      : $LOG_DIR/agent.log"
        echo " Install log    : $LOG_FILE"
        echo ""
        echo " Commands:"
        echo "   Stop    : launchctl unload $PLIST_PATH"
        echo "   Start   : launchctl load   $PLIST_PATH"
        echo "   Restart : launchctl kickstart -k gui/\$(id -u)/com.printhub.agent"
        echo "═══════════════════════════════════════════════════════════"
        echo "SUCCESS" >> "$LOG_FILE"
    else
        echo ""
        echo "[WARNING] Agent process not detected after start." | tee -a "$LOG_FILE"
        echo "          Run manually to see errors:"
        echo "            $VENV_PY $DIR/agent.py"
        echo "          Or check: $LOG_DIR/agent.log"
    fi

# ── Linux systemd service ─────────────────────────────────────────
else
    UNIT_FILE="/etc/systemd/system/printhub-agent.service"
    echo "[STEP 4] Creating systemd service (requires sudo)..." | tee -a "$LOG_FILE"

    sudo tee "$UNIT_FILE" >/dev/null <<EOF
[Unit]
Description=PrintHub USB Print Agent
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=${DIR}
ExecStart=${DIR}/venv/bin/python3 ${DIR}/agent.py
Restart=always
RestartSec=10
StandardOutput=append:${LOG_DIR}/agent.log
StandardError=append:${LOG_DIR}/agent.log

[Install]
WantedBy=multi-user.target
EOF

    if [ $? -ne 0 ]; then
        echo "[ERROR] Failed to create systemd unit file." | tee -a "$LOG_FILE"
        echo "        Make sure you have sudo rights." | tee -a "$LOG_FILE"
        echo "Press Enter to close..."
        read -r
        exit 1
    fi

    echo "[STEP 5] Enabling and starting service..." | tee -a "$LOG_FILE"
    sudo systemctl daemon-reload
    sudo systemctl enable printhub-agent
    sudo systemctl start printhub-agent
    if [ $? -ne 0 ]; then
        echo "[WARNING] systemctl start returned an error." | tee -a "$LOG_FILE"
        echo "          Check: journalctl -u printhub-agent -n 50" | tee -a "$LOG_FILE"
    fi

    sleep 2
    if sudo systemctl is-active printhub-agent &>/dev/null; then
        echo "" | tee -a "$LOG_FILE"
        echo "═══════════════════════════════════════════════════════════"
        echo " SUCCESS! PrintHub Agent is installed and running."
        echo " It starts automatically at boot."
        echo ""
        echo " Install folder : $DIR"
        echo " Agent log      : $LOG_DIR/agent.log"
        echo " Install log    : $LOG_FILE"
        echo ""
        echo " Commands:"
        echo "   sudo systemctl stop    printhub-agent"
        echo "   sudo systemctl start   printhub-agent"
        echo "   sudo systemctl restart printhub-agent"
        echo "   sudo systemctl disable printhub-agent"
        echo "   journalctl -u printhub-agent -f"
        echo "═══════════════════════════════════════════════════════════"
        echo "SUCCESS" >> "$LOG_FILE"
    else
        echo ""
        echo "[WARNING] Agent process not detected after start." | tee -a "$LOG_FILE"
        echo "          Check: journalctl -u printhub-agent -n 50"
        echo "          Or:    tail -f $LOG_DIR/agent.log"
    fi
fi

echo ""
echo "Install log: $LOG_FILE"
echo ""
