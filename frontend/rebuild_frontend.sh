#!/bin/bash
# PrintHub Frontend - Rebuild production bundle
# Run this whenever you change the server IP in .env
cd "$(dirname "$0")"

echo ""
echo "==========================================================="
echo " PrintHub Frontend - Rebuild Production Bundle"
echo " Run this whenever you change the server IP in .env"
echo "==========================================================="
echo ""

# ── Show current VITE_API_URL ──────────────────────────────────
CURRENT_URL=$(grep -i "VITE_API_URL" .env 2>/dev/null || echo "Not found")
echo "[INFO] Current setting: $CURRENT_URL"
echo ""
echo "[INFO] If the server IP is wrong, press Ctrl+C now,"
echo "       edit frontend/.env and change VITE_API_URL, then run this again."
echo ""
read -p "Press Enter to continue with the rebuild..."

# ── Delete old build ───────────────────────────────────────────
if [ -d "dist" ]; then
    echo "[INFO] Removing old build..."
    rm -rf dist
fi

# ── Build ──────────────────────────────────────────────────────
echo "[INFO] Building... (this takes 30-60 seconds)"
echo ""
npm run build
if [ $? -ne 0 ]; then
    echo ""
    echo "[ERROR] Build failed. Check the errors above."
    read -p "Press Enter to close..."
    exit 1
fi

echo ""
echo "==========================================================="
echo " Build complete!"
echo " Now run ./start_frontend.sh to start the dashboard."
echo "==========================================================="
echo ""
