'use client';

import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { authHeaders, buildApiUrl } from '@/lib/api';
import { useAuthStore } from '@/stores/useAuthStore';
import { useCameraStore } from '@/stores/useCameraStore';

export function useStatusPoller() {
    const token = useAuthStore((state) => state.token);
    const setSystemStatus = useCameraStore((state) => state.setSystemStatus);

    const { data } = useQuery({
        queryKey: ['system-status', token],
        queryFn: async () => {
            const resp = await fetch(buildApiUrl('/api/status'), {
                headers: authHeaders({ token }),
            });
            if (!resp.ok) throw new Error('Failed to fetch status');
            return resp.json();
        },
        enabled: false,
    });

    useEffect(() => {
        if (data && data.system) {
            setSystemStatus({
                status: data.status ?? 'degraded',
                gpu_util: data.gpu?.utilization ?? 0,
                gpu_mem: data.gpu?.used ?? 0,
                gpu_temp: data.gpu?.temperature ?? 0,
                cpu_usage: data.system?.cpu_usage ?? 0,
                ram_usage: data.system?.ram_usage ?? 0,
            });
        }
    }, [data, setSystemStatus]);

    return { status: data };
}
