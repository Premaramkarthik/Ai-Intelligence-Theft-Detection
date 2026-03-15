import { create } from 'zustand';
import type { Camera, SystemStatus } from '@/types/view-models';

interface CameraState {
    cameras: Record<string, Camera>;
    systemStatus: SystemStatus | null;
    logs: string[];

    setSystemStatus: (status: SystemStatus) => void;
    setCameras: (cameras: Record<string, Camera>) => void;
    mergeCameras: (cameras: Record<string, Camera>) => void;
    updateCamera: (id: string, updates: Partial<Camera>) => void;
    addCamera: (camera: Camera) => void;
    removeCamera: (id: string) => void;
    addLog: (log: string) => void;
}

export const useCameraStore = create<CameraState>((set) => ({
    cameras: {},
    systemStatus: null,
    logs: [],

    setSystemStatus: (status) => set({ systemStatus: status }),
    setCameras: (cameras) => set({ cameras }),
    mergeCameras: (cameras) => set((state) => {
        const merged: Record<string, Camera> = {};
        Object.entries(cameras).forEach(([id, camera]) => {
            const existing = state.cameras[id];
            merged[id] = {
                ...camera,
                ...existing,
                ...camera,
                name: existing?.name ?? camera.name,
                store_id: existing?.store_id ?? camera.store_id,
                organization_id: existing?.organization_id ?? camera.organization_id,
                lastDetection: existing?.lastDetection ?? camera.lastDetection,
            };
        });
        return { cameras: merged };
    }),

    updateCamera: (id, updates) => set((state) => ({
        cameras: {
            ...state.cameras,
            [id]: { ...state.cameras[id], ...updates }
        }
    })),

    addCamera: (camera) => set((state) => ({
        cameras: { ...state.cameras, [camera.id]: camera }
    })),

    removeCamera: (id) => set((state) => {
        const remaining = { ...state.cameras };
        delete remaining[id];
        return { cameras: remaining };
    }),

    addLog: (log) => set((state) => ({
        logs: [log, ...state.logs].slice(0, 100)
    }))
}));
