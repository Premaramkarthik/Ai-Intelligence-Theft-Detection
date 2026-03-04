'use client';

import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useCameraStore } from '@/stores/useCameraStore';

export function useCamerasSynchronizer() {
    const setCameras = useCameraStore((state) => state.setCameras);

    const { data: sources, isLoading } = useQuery({
        queryKey: ['camera-sources'],
        queryFn: async () => {
            const resp = await fetch('http://localhost:9001/api/cameras');
            if (!resp.ok) throw new Error('Failed to fetch camera sources');
            return resp.json() as Promise<Record<string, string>>;
        },
        refetchInterval: 10000, // Sync every 10 seconds
    });

    useEffect(() => {
        if (sources) {
            const formattedCameras: any = {};
            Object.entries(sources).forEach(([id, url]) => {
                formattedCameras[id] = {
                    id,
                    name: id.toUpperCase().replace('_', ' '),
                    url,
                    status: 'online' as const
                };
            });
            setCameras(formattedCameras);
        }
    }, [sources, setCameras]);

    return { isLoading };
}
