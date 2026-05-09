import { useEffect, useRef, useCallback } from "react";
import { useAuth } from "../context/AuthContext";
import { WS_BASE_URL } from "../config";

/**
 * Auto-reconnecting WebSocket hook with exponential backoff.
 *
 * @param {(msg: {type: string, data: object}) => void} onMessage  - Called for every server push
 * @param {boolean} enabled - Set false to disable (e.g. while logged out)
 */
export function useWebSocket(onMessage, enabled = true) {
    const { token } = useAuth();
    const wsRef = useRef(null);
    const retryRef = useRef(0);
    const timerRef = useRef(null);
    const mountedRef = useRef(true);
    const onMessageRef = useRef(onMessage);

    // Keep the callback ref current without re-connecting on each render
    useEffect(() => {
        onMessageRef.current = onMessage;
    }, [onMessage]);

    const connect = useCallback(() => {
        if (!mountedRef.current || !token) return;

        const url = `${WS_BASE_URL}/ws?token=${encodeURIComponent(token)}`;
        const ws = new WebSocket(url);
        wsRef.current = ws;

        ws.onopen = () => {
            retryRef.current = 0;
        };

        ws.onmessage = (e) => {
            try {
                const msg = JSON.parse(e.data);
                onMessageRef.current(msg);
            } catch {
                // ignore malformed frames
            }
        };

        ws.onclose = () => {
            if (!mountedRef.current) return;
            // Exponential backoff: 1s, 2s, 4s, 8s … capped at 30s
            const delay = Math.min(1000 * Math.pow(2, retryRef.current), 30000);
            retryRef.current += 1;
            timerRef.current = setTimeout(connect, delay);
        };

        ws.onerror = () => {
            // onclose fires after onerror, so reconnect is handled there
            ws.close();
        };
    }, [token]);

    useEffect(() => {
        if (!enabled || !token) return;
        mountedRef.current = true;
        connect();

        return () => {
            mountedRef.current = false;
            clearTimeout(timerRef.current);
            if (wsRef.current) {
                wsRef.current.onclose = null; // prevent reconnect on intentional close
                wsRef.current.close();
            }
        };
    }, [connect, enabled, token]);
}
