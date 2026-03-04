'use client';

import Sidebar from './Sidebar';
import { useCamerasSynchronizer } from '@/hooks/useCamerasSynchronizer';
import { useSystemStatusWebSocket } from '@/hooks/useSystemStatusWebSocket';

export default function DashboardShell({ children }: { children: React.ReactNode }) {
    // Initialize real-time sync and telemetry
    useCamerasSynchronizer();
    useSystemStatusWebSocket();

    return (
        <div className="flex bg-slate-950 min-h-screen">
            <Sidebar />
            <main className="flex-1 flex flex-col overflow-hidden">
                <header className="h-16 border-b border-slate-800 flex items-center justify-between px-8 bg-slate-900/50 backdrop-blur-sm">
                    <div className="flex items-center gap-4">
                        <h2 className="text-xl font-semibold text-slate-100 uppercase tracking-wide">Surveillance Central</h2>
                        <div className="flex items-center gap-2 px-2 py-0.5 bg-emerald-500/10 border border-emerald-500/20 rounded text-[10px] font-bold text-emerald-500 animate-pulse">
                            SYS-OK
                        </div>
                    </div>

                    <div className="flex items-center gap-4">
                        {/* Action buttons could go here */}
                        <div className="text-slate-500 text-sm font-medium">
                            Mode: <span className="text-blue-400">D1-D5 Staged Inference</span>
                        </div>
                    </div>
                </header>

                <section className="flex-1 overflow-y-auto p-8 custom-scrollbar">
                    {children}
                </section>
            </main>
        </div>
    );
}
