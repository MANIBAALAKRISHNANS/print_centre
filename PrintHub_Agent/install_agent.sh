#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# PrintHub Agent — macOS / Linux Installer
# ═══════════════════════════════════════════════════════════════
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

OS="$(uname -s)"
PLIST_PATH="$HOME/Library/LaunchAgents/com.printhub.agent.plist"
LOG_DIR="$HOME/Library/Logs/PrintHubAgent"

echo ""
echo "═══════════════════════════════════════════════════════════"
echo " PrintHub Print Agent — Installer"
echo "═══════════════════════════════════════════════════════════"
echo ""

# ── Check Python ─────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "[ERROR] Python 3 not found."
    echo "        macOS: brew install python"
    echo "        Ubuntu: sudo apt install python3 python3-venv"
    exit 1
fi
PY_VER="$(python3 --version 2>&1)"
echo "[OK] $PY_VER"

# ── Create log directory ─────────────────────────────────────────
mkdir -p "$LOG_DIR"
chmod 700 "$LOG_DIR"
echo "[OK] Log directory: $LOG_DIR"

# ── Virtual environment ─────────────────────────────────────────
if [ ! -d "$DIR/venv" ]; then
    echo "[STEP 1] Creating virtual environment..."
    python3 -m venv "$DIR/venv"
fi
echo "[OK] Virtual environment ready."

# ── Install dependencies ─────────────────────────────────────────
echo "[STEP 2] Installing dependencies..."
source "$DIR/venv/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet -r "$DIR/requirements.txt"
echo "[OK] Dependencies installed (including websocket-client for real-time)."

# ── First-time setup ────────────────────────────────────────────
if [ ! -f "$DIR/agent_config.json" ]; then
    echo ""
    echo "═══════════════════════════════════════════════════════════"
    echo " SETUP — Connect this workstation to PrintHub Server"
    echo "═══════════════════════════════════════════════════════════"
    echo ""
    read -rp "  Server IP address (e.g. 192.168.1.50): " SERVER_IP
    read -rp "  Server port [8000]: " SERVER_PORT
    SERVER_PORT="${SERVER_PORT:-8000}"

    read -rp "  Use HTTPS? (y/N): " USE_HTTPS
    if [[ "${USE_HTTPS,,}" == "y" ]]; then
        PROTO="https"
        read -rp "  Skip TLS certificate verification for self-signed cert? (y/N): " SKIP_TLS
        [[ "${SKIP_TLS,,}" == "y" ]] && NV_FLAG="--no-verify" || NV_FLAG=""
    else
        PROTO="http"
        NV_FLAG=""
    fi
    SERVER_URL="${PROTO}://${SERVER_IP}:${SERVER_PORT}"

    echo ""
    echo "  Open the PrintHub dashboard > Agents > Generate Code"
    read -rp "  Enter the 8-character activation code: " ACT_CODE

    echo ""
    echo "  Saving activation code for $SERVER_URL..."
    python3 "$DIR/agent_setup.py" --code "$ACT_CODE" --server "$SERVER_URL" $NV_FLAG
else
    echo "[OK] Existing configuration found — skipping setup."
fi

# ── macOS launchd service ────────────────────────────────────────
if [ "$OS" = "Darwin" ]; then
    # Unload any existing instance
    if launchctl list 2>/dev/null | grep -q "com.printhub.agent"; then
        echo "[STEP 3] Removing existing launchd service..."
        launchctl unload "$PLIST_PATH" 2>/dev/null || true
    fi

    echo "[STEP 3] Creating launchd service..."
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

    chmod 644 "$PLIST_PATH"
    echo "[STEP 4] Starting service..."
    launchctl load "$PLIST_PATH"

    sleep 2
    if launchctl list 2>/dev/null | grep -q "com.printhub.agent"; then
        echo ""
        echo "═══════════════════════════════════════════════════════════"
        echo " SUCCESS! PrintHub Agent is running as a launchd service."
        echo " It starts automatically at login."
        echo ""
        echo " Logs:"
        echo "   tail -f $LOG_DIR/agent.log"
        echo ""
        echo " Commands:"
        echo "   Stop    : launchctl unload $PLIST_PATH"
        echo "   Start   : launchctl load   $PLIST_PATH"
        echo "   Restart : launchctl kickstart -k gui/\$(id -u)/com.printhub.agent"
        echo "   Status  : python3 $DIR/agent_setup.py --status"
        echo "   Remove  : launchctl unload $PLIST_PATH && rm $PLIST_PATH"
        echo "═══════════════════════════════════════════════════════════"
    else
        echo "[WARNING] Service may not have started. Check:"
        echo "  tail -f $LOG_DIR/agent.log"
    fi

# ── Linux systemd service ─────────────────────────────────────────
else
    UNIT_FILE="/etc/systemd/system/printhub-agent.service"
    echo "[STEP 3] Creating systemd service (requires sudo)..."
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

    echo "[STEP 4] Enabling and starting service..."
    sudo systemctl daemon-reload
    sudo systemctl enable printhub-agent
    sudo systemctl start printhub-agent

    sleep 2
    if sudo systemctl is-active printhub-agent &>/dev/null; then
        echo ""
        echo "═══════════════════════════════════════════════════════════"
        echo " SUCCESS! PrintHub Agent is running as a systemd service."
        echo ""
        echo " Logs   : journalctl -u printhub-agent -f"
        echo "          tail -f $LOG_DIR/agent.log"
        echo ""
        echo " Commands:"
        echo "   sudo systemctl stop    printhub-agent"
        echo "   sudo systemctl start   printhub-agent"
        echo "   sudo systemctl restart printhub-agent"
        echo "   sudo systemctl disable printhub-agent"
        echo "═══════════════════════════════════════════════════════════"
    else
        echo "[WARNING] Service may not have started. Check:"
        echo "  journalctl -u printhub-agent -n 50"
    fi
fi
