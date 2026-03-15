'use client';

import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { authHeaders, buildApiUrl, withApiCredentials } from '@/lib/api';
import { toSystemStatus } from '@/lib/systemStatus';
import { useAuthStore } from '@/stores/useAuthStore';
import { useCameraStore } from '@/stores/useCameraStore';
import type { SystemStatusMessage } from '@/types/contracts';

export function useStatusPoller() {
    const token = useAuthStore((state) => state.token);
    const setSystemStatus = useCameraStore((state) => state.setSystemStatus);

    const { data } = useQuery({
        queryKey: ['system-status', token],
        queryFn: async () => {
            const resp = await fetch(buildApiUrl('/api/status'), {
                ...withApiCredentials(),
                headers: authHeaders({ token }),
            });
            if (!resp.ok) throw new Error('Failed to fetch status');
            return resp.json() as Promise<SystemStatusMessage>;
        },
        enabled: false,
    });

    useEffect(() => {
        if (data) {
            setSystemStatus(toSystemStatus(data));
        }
    }, [data, setSystemStatus]);

    return { status: data };
}
