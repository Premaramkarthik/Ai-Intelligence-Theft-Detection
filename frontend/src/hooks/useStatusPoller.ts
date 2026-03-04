'use client';

import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useCameraStore } from '@/stores/useCameraStore';

export function useStatusPoller() {
    const setSystemStatus = useCameraStore((state) => state.setSystemStatus);

    const { data } = useQuery({
        queryKey: ['system-status'],
        queryFn: async () => {
            const resp = await fetch('http://localhost:9001/api/status');
            if (!resp.ok) throw new Error('Failed to fetch status');
            return resp.json();
        },
        enabled: false, // Disabled in favor of useSystemStatusWebSocket
    });

    useEffect(() => {
        if (data && data.system) {
            setSystemStatus({
                gpu_util: data.system.gpu?.utilization ?? 0,
                gpu_mem: data.system.gpu?.memory_used ?? 0,
                gpu_temp: data.system.gpu?.temperature ?? 0,
                cpu_usage: data.system.cpu?.usage ?? 0,
                ram_usage: data.system.ram?.usage ?? 0,
            });
        }
    }, [data, setSystemStatus]);

    return { status: data };
}
