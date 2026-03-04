'use client';

import { useEffect } from 'react';
import { useCameraStore } from '@/stores/useCameraStore';

export function useSystemStatusWebSocket() {
    const setSystemStatus = useCameraStore((state) => state.setSystemStatus);

    useEffect(() => {
        const socket = new WebSocket('ws://localhost:9001/ws/status');

        socket.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.system) {
                    setSystemStatus({
                        gpu_util: data.gpu?.utilization ?? 0,
                        gpu_mem: data.gpu?.used ?? 0,
                        gpu_temp: data.gpu?.temperature ?? 0, // Backend doesn't have it yet, using 0
                        cpu_usage: data.system.cpu_usage ?? 0,
                        ram_usage: data.system.ram_usage ?? 0,
                    });
                }
            } catch (err) {
                console.error('Failed to parse system status', err);
            }
        };

        socket.onerror = (err) => {
            console.error('System Status WebSocket error', err);
        };

        return () => socket.close();
    }, [setSystemStatus]);
}
