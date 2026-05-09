// API Configuration
// NOTE: Use 127.0.0.1 (not 'localhost') to force IPv4.
// On Windows, Vite binds to [::1] (IPv6), causing 'localhost' to resolve
// to ::1 in the browser, while the backend is only on 127.0.0.1 (IPv4).
// This mismatch causes a "Failed to fetch" network error.
export const API_BASE_URL =
    import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

// WebSocket base URL — derived from VITE_API_URL by swapping http→ws
export const WS_BASE_URL = (() => {
    const base = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";
    return base.replace(/^http/, "ws");
})();