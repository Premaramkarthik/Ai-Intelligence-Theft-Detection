'use client';

import DashboardShell from '@/components/layout/DashboardShell';
import { Camera, Shield } from 'lucide-react';

export default function CamerasPage() {
    return (
        <DashboardShell>
            <div className="flex flex-col gap-8">
                <div>
                    <h1 className="text-3xl font-bold text-white tracking-tight">Camera Management</h1>
                    <p className="text-slate-500 mt-1">Configure individual vision parameters and regions of interest.</p>
                </div>

                <div className="flex flex-col items-center justify-center py-40 bg-slate-900/50 rounded-3xl border border-slate-800 border-dashed">
                    <Camera className="w-16 h-16 text-slate-700 mb-6" />
                    <h2 className="text-xl font-bold text-white">Enhanced Configuration Coming Soon</h2>
                    <p className="text-slate-500 mt-2 max-w-sm text-center">
                        Future updates will allow per-camera ROI drawing and advanced staged-inference thresholding.
                    </p>
                </div>
            </div>
        </DashboardShell>
    );
}
