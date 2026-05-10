#!/bin/bash
# PrintHub Backend - Mac/Linux startup script
cd "$(dirname "$0")"

echo ""
echo "==========================================================="
echo " PrintHub Backend Server"
echo "==========================================================="
echo ""

# ── Apply macOS firewall rules ─────────────────────────────────
PYTHON_PATH="$(pwd)/venv/bin/python3"
if [[ "$(uname)" == "Darwin" ]]; then
    echo "[INFO] Applying macOS firewall rules (you may be asked for your password)..."
    sudo /usr/libexec/ApplicationFirewall/socketfilterfw --add "$PYTHON_PATH" 2>/dev/null
    sudo /usr/libexec/ApplicationFirewall/socketfilterfw --unblockapp "$PYTHON_PATH" 2>/dev/null
    echo "[OK] Firewall rules applied."
    echo ""
fi

# ── Show server IP ─────────────────────────────────────────────
if [[ "$(uname)" == "Darwin" ]]; then
    SERVER_IP=$(ipconfig getifaddr en0 2>/dev/null || echo "unknown")
else
    SERVER_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "unknown")
fi

echo " Local:   http://127.0.0.1:8000"
echo " Network: http://$SERVER_IP:8000"
echo " Press Ctrl+C to stop"
echo ""

# ── Start backend ──────────────────────────────────────────────
venv/bin/python3 -m uvicorn main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --timeout-keep-alive 75 \
    --ws-ping-interval 20 \
    --ws-ping-timeout 30
