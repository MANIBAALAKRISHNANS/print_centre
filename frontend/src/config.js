// API Configuration
// Derives the backend URL from the browser's current hostname so the same
// build works from localhost, the server's WiFi IP, the hotspot IP (192.168.137.1),
// or any future IP — no rebuild needed when the server IP changes.
// 'localhost' is mapped to '127.0.0.1' to force IPv4 on Windows (Vite binds
// to [::1] by default, causing "Failed to fetch" on IPv4-only backends).
const _hostname = window.location.hostname === "localhost"
    ? "127.0.0.1"
    : window.location.hostname;
const _origin = `${window.location.protocol}//${_hostname}:8000`;

export const API_BASE_URL = _origin;
export const WS_BASE_URL  = _origin.replace(/^http/, "ws");