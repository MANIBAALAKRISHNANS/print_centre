#!/bin/bash
# PrintHub Frontend - Mac/Linux startup script
cd "$(dirname "$0")"

echo ""
echo "==========================================================="
echo " PrintHub Frontend (Dashboard)"
echo "==========================================================="
echo ""

# ── Apply macOS firewall rules ─────────────────────────────────
if [[ "$(uname)" == "Darwin" ]]; then
    NODE_PATH="$(which node)"
    echo "[INFO] Applying macOS firewall rules (you may be asked for your password)..."
    sudo /usr/libexec/ApplicationFirewall/socketfilterfw --add "$NODE_PATH" 2>/dev/null
    sudo /usr/libexec/ApplicationFirewall/socketfilterfw --unblockapp "$NODE_PATH" 2>/dev/null
    echo "[OK] Firewall rules applied."
    echo ""
fi

# ── Check if production build exists ──────────────────────────
if [ ! -f "dist/index.html" ]; then
    echo "[INFO] No production build found. Building now..."
    echo "[INFO] This takes about 30-60 seconds. Please wait..."
    echo ""
    npm run build
    if [ $? -ne 0 ]; then
        echo ""
        echo "[ERROR] Build failed. Check the errors above."
        echo "[INFO]  Make sure you ran: npm install"
        echo "[INFO]  And that frontend/.env has the correct VITE_API_URL"
        read -p "Press Enter to close..."
        exit 1
    fi
    echo ""
    echo "[OK] Build complete."
fi

# ── Get server IP ──────────────────────────────────────────────
SERVER_IP=$(grep -i "VITE_API_URL" .env 2>/dev/null | sed 's|.*//||' | cut -d: -f1)
if [ -z "$SERVER_IP" ]; then
    if [[ "$(uname)" == "Darwin" ]]; then
        SERVER_IP=$(ipconfig getifaddr en0 2>/dev/null || echo "your-mac-ip")
    else
        SERVER_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "your-server-ip")
    fi
fi

echo "[OK] Serving production build on ALL network interfaces, port 5173"
echo ""
echo " Dashboard (this Mac)  : http://localhost:5173"
echo " Dashboard (network)   : http://$SERVER_IP:5173"
echo ""
echo " This is a stable production server."
echo " Press Ctrl+C to stop."
echo ""

# ── Start server bound to ALL interfaces ──────────────────────
npx serve -s dist -l tcp://0.0.0.0:5173
