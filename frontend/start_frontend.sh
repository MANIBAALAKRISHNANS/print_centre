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
    PYTHON_PATH="$(which python3)"
    echo "[INFO] Applying macOS firewall rules (you may be asked for your password)..."
    sudo /usr/libexec/ApplicationFirewall/socketfilterfw --add "$PYTHON_PATH" 2>/dev/null
    sudo /usr/libexec/ApplicationFirewall/socketfilterfw --unblockapp "$PYTHON_PATH" 2>/dev/null
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

# ── Start server (Python SPA server — binds to 0.0.0.0 guaranteed) ──
python3 serve_spa.py
