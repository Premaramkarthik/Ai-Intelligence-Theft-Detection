'use client';

import { useEffect } from 'react';

import AuthPanel from '@/components/auth/AuthPanel';
import { useCamerasSynchronizer } from '@/hooks/useCamerasSynchronizer';
import { useSystemStatusWebSocket } from '@/hooks/useSystemStatusWebSocket';
import { useAuthStore } from '@/stores/useAuthStore';
import { useCameraStore } from '@/stores/useCameraStore';

import Sidebar from './Sidebar';

export default function DashboardShell({ children }: { children: React.ReactNode }) {
  const hydrate = useAuthStore((state) => state.hydrate);
  const token = useAuthStore((state) => state.token);
  const hydrated = useAuthStore((state) => state.hydrated);
  const systemStatus = useCameraStore((state) => state.systemStatus);

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  useCamerasSynchronizer();
  useSystemStatusWebSocket();

  if (!hydrated) {
    return <div className="min-h-screen bg-slate-950" />;
  }

  if (!token) {
    return <AuthPanel />;
  }

  const statusLabel = systemStatus?.status === 'healthy' ? 'Backend Ready' : 'Backend Degraded';
  const statusClass =
    systemStatus?.status === 'healthy'
      ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-400'
      : 'border-amber-500/20 bg-amber-500/10 text-amber-300';

  return (
    <div className="flex min-h-screen bg-slate-950">
      <Sidebar />
      <main className="flex flex-1 flex-col overflow-hidden">
        <header className="flex h-16 items-center justify-between border-b border-slate-800 bg-slate-900/50 px-8 backdrop-blur-sm">
          <div className="flex items-center gap-4">
            <h2 className="text-xl font-semibold uppercase tracking-wide text-slate-100">Surveillance Central</h2>
            <div className={`rounded border px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.2em] ${statusClass}`}>
              {statusLabel}
            </div>
          </div>

          <div className="text-sm font-medium text-slate-500">
            Mode: <span className="text-blue-400">D1-D5 Staged Inference</span>
          </div>
        </header>

        <section className="flex-1 overflow-y-auto p-8 custom-scrollbar">{children}</section>
      </main>
    </div>
  );
}
