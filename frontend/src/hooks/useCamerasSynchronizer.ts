'use client';

import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';

import { authHeaders, buildApiUrl } from '@/lib/api';
import { useAuthStore } from '@/stores/useAuthStore';
import { useCameraStore } from '@/stores/useCameraStore';

export function useCamerasSynchronizer() {
  const token = useAuthStore((state) => state.token);
  const setCameras = useCameraStore((state) => state.setCameras);

  const { data: sources } = useQuery({
    queryKey: ['camera-sources', token],
    enabled: Boolean(token),
    queryFn: async () => {
      const response = await fetch(buildApiUrl('/api/cameras/'), {
        headers: authHeaders({ token }),
      });
      if (!response.ok) {
        throw new Error('Failed to fetch camera sources');
      }
      return response.json() as Promise<Record<string, string>>;
    },
    refetchInterval: 10000,
  });

  useEffect(() => {
    if (!sources) {
      return;
    }
    const formattedCameras: Record<string, { id: string; name: string; url: string; status: 'online' }> = {};
    Object.entries(sources).forEach(([id, url]) => {
      formattedCameras[id] = {
        id,
        name: id.toUpperCase().replaceAll('_', ' '),
        url,
        status: 'online',
      };
    });
    setCameras(formattedCameras);
  }, [setCameras, sources]);
}
