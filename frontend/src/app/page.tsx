'use client';

import { useState } from 'react';
import DashboardShell from '@/components/layout/DashboardShell';
import { Camera, Plus } from 'lucide-react';
import ConnectionModal from '@/components/dashboard/ConnectionModal';
import StreamCard from '@/components/dashboard/StreamCard';
import { useCameraStore } from '@/stores/useCameraStore';

export default function Home() {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const cameras = useCameraStore((state) => state.cameras);
  const cameraList = Object.values(cameras);

  return (
    <DashboardShell>
      <div className="flex flex-col gap-8">
        <div className="flex justify-between items-end">
          <div>
            <h1 className="text-3xl font-bold text-white tracking-tight">Active Monitors</h1>
            <p className="text-slate-500 mt-1">Real-time fusion of computer vision and hardware metrics.</p>
          </div>

          <button
            onClick={() => setIsModalOpen(true)}
            className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 text-white px-5 py-2.5 rounded-xl font-semibold transition-all active:scale-95 shadow-lg shadow-blue-600/20"
          >
            <Plus className="w-5 h-5" />
            Connect Camera
          </button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6">
          {cameraList.length > 0 ? (
            cameraList.map((cam) => (
              <StreamCard key={cam.id} id={cam.id} name={cam.name} />
            ))
          ) : (
            <EmptyState />
          )}
        </div>
      </div>

      <ConnectionModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
      />
    </DashboardShell>
  );
}

function EmptyState() {
  return (
    <div className="col-span-full py-32 flex flex-col items-center justify-center border-2 border-dashed border-slate-800 rounded-3xl bg-slate-900/20">
      <div className="w-16 h-16 bg-slate-800 rounded-2xl flex items-center justify-center text-slate-500 mb-6">
        <Camera className="w-8 h-8" />
      </div>
      <h3 className="text-xl font-bold text-white">No active streams</h3>
      <p className="text-slate-500 mt-2 max-w-xs text-center">
        Initialize a hardware connection to start real-time inference monitoring.
      </p>
    </div>
  );
}
