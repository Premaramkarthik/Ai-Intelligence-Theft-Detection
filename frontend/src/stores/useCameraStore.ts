import { create } from 'zustand';

interface Camera {
    id: string;
    name: string;
    url: string;
    status: 'online' | 'offline' | 'connecting';
    lastDetection?: string;
}

interface SystemStatus {
    gpu_util: number;
    gpu_mem: number;
    gpu_temp: number;
    cpu_usage: number;
    ram_usage: number;
}

interface CameraState {
    cameras: Record<string, Camera>;
    systemStatus: SystemStatus | null;
    logs: string[];

    setSystemStatus: (status: SystemStatus) => void;
    setCameras: (cameras: Record<string, Camera>) => void;
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
        const { [id]: _, ...remaining } = state.cameras;
        return { cameras: remaining };
    }),

    addLog: (log) => set((state) => ({
        logs: [log, ...state.logs].slice(0, 100)
    }))
}));
