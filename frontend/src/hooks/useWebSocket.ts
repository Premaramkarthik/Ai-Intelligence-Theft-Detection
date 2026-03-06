import { useEffect, useRef, useState } from "react";

export function useWebSocket<T>(url: string) {
    const [data, setData] = useState<T | null>(null);
    const [isConnected, setIsConnected] = useState(false);
    const wsRef = useRef<WebSocket | null>(null);

    useEffect(() => {
        const wsUrl = `ws://localhost:9001${url}`;
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => setIsConnected(true);
        ws.onmessage = (event) => {
            try {
                const parsed = JSON.parse(event.data);
                setData(parsed);
            } catch (err) {
                console.error("WebSocket payload error:", err);
            }
        };
        ws.onclose = () => setIsConnected(false);

        return () => {
            ws.close();
            wsRef.current = null;
        };
    }, [url]);

    return { data, isConnected };
}
