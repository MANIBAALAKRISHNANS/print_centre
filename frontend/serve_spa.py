"""
PrintHub SPA server — serves the React production build on 0.0.0.0:5173.
Falls back to index.html for any unknown path (required for React Router).
Uses only Python standard library — no npm or extra packages needed.
"""
import http.server
import os
import sys
import socket

PORT = 5173
DIST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist")

MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js":   "application/javascript",
    ".css":  "text/css",
    ".png":  "image/png",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg":  "image/svg+xml",
    ".ico":  "image/x-icon",
    ".json": "application/json",
    ".woff": "font/woff",
    ".woff2":"font/woff2",
    ".ttf":  "font/ttf",
    ".map":  "application/json",
}

class SPAHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIST_DIR, **kwargs)

    def do_GET(self):
        # Strip query string for file resolution
        clean_path = self.path.split("?")[0].split("#")[0]
        full_path = os.path.join(DIST_DIR, clean_path.lstrip("/"))

        # If the exact file exists, serve it normally
        if os.path.isfile(full_path):
            return super().do_GET()

        # Otherwise serve index.html so React Router handles the route
        self.path = "/index.html"
        return super().do_GET()

    def guess_type(self, path):
        ext = os.path.splitext(path)[1].lower()
        return MIME_TYPES.get(ext, "application/octet-stream")

    def log_message(self, fmt, *args):
        # Suppress per-request noise — only show errors
        if args and len(args) >= 2 and str(args[1]).startswith(("4", "5")):
            print(f"  [{args[1]}] {args[0]}")


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "YOUR_SERVER_IP"


if __name__ == "__main__":
    if not os.path.isfile(os.path.join(DIST_DIR, "index.html")):
        print("[ERROR] dist/index.html not found.")
        print("[INFO]  Run 'npm run build' first, then start again.")
        sys.exit(1)

    local_ip = get_local_ip()

    server = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), SPAHandler)

    print()
    print("===========================================================")
    print(" PrintHub Frontend — serving production build")
    print("===========================================================")
    print()
    print(f"  Dashboard (this PC)   :  http://localhost:{PORT}")
    print(f"  Dashboard (network)   :  http://{local_ip}:{PORT}")
    print()
    print("  Bound to 0.0.0.0 — all network interfaces are open.")
    print("  Press Ctrl+C to stop.")
    print()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[INFO] Server stopped.")
        server.server_close()
