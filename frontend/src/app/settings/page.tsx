'use client';

import DashboardShell from '@/components/layout/DashboardShell';
import { Settings as SettingsIcon, Sliders } from 'lucide-react';

export default function SettingsPage() {
    return (
        <DashboardShell>
            <div className="flex flex-col gap-8">
                <div>
                    <h1 className="text-3xl font-bold text-white tracking-tight">System Settings</h1>
                    <p className="text-slate-500 mt-1">Global AI orchestrator and telemetry configurations.</p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div className="p-8 bg-slate-900 border border-slate-800 rounded-3xl opacity-50 cursor-not-allowed">
                        <Sliders className="w-8 h-8 text-blue-500 mb-4" />
                        <h3 className="text-lg font-bold text-white uppercase tracking-tight">Inference Tuning</h3>
                        <p className="text-slate-500 text-sm mt-1">Adjust SHM ring buffer slots and GPU worker threads.</p>
                    </div>

                    <div className="p-8 bg-slate-900 border border-slate-800 rounded-3xl flex flex-col items-center justify-center text-center py-20">
                        <SettingsIcon className="w-12 h-12 text-slate-800 mb-4 animate-spin-slow" />
                        <span className="text-xs font-bold text-slate-500 uppercase tracking-[0.3em]">V0.2.0-ALFA</span>
                    </div>
                </div>
            </div>
        </DashboardShell>
    );
}
