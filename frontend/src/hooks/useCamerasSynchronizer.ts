'use client';

import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';

import { authHeaders, buildApiUrl, withApiCredentials } from '@/lib/api';
import { isAuthFailure } from '@/lib/auth';
import { useAuthStore } from '@/stores/useAuthStore';
import { useCameraStore } from '@/stores/useCameraStore';
import type { CameraSourcesResponse } from '@/types/contracts';
import type { Camera } from '@/types/view-models';

export function useCamerasSynchronizer() {
  const token = useAuthStore((state) => state.token);
  const logout = useAuthStore((state) => state.logout);
  const mergeCameras = useCameraStore((state) => state.mergeCameras);

  const { data: sources } = useQuery({
    queryKey: ['camera-sources', token],
    enabled: Boolean(token),
    queryFn: async () => {
      const response = await fetch(buildApiUrl('/api/cameras/'), {
        ...withApiCredentials(),
        headers: authHeaders({ token }),
      });
      if (!response.ok) {
        const body = (await response.json().catch(() => ({}))) as { detail?: string };
        if (isAuthFailure(response.status, body.detail)) {
          logout();
          return {};
        }
        throw new Error('Failed to fetch camera sources');
      }
      return response.json() as Promise<CameraSourcesResponse>;
    },
    refetchInterval: 10000,
  });

  useEffect(() => {
    if (!sources) {
      return;
    }
    const formattedCameras: Record<string, Camera> = {};
    Object.entries(sources).forEach(([id, url]) => {
      formattedCameras[id] = {
        id,
        name: id.toUpperCase().replaceAll('_', ' '),
        url,
        status: 'online',
      };
    });
    mergeCameras(formattedCameras);
  }, [mergeCameras, sources]);
}
