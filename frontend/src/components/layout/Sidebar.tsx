'use client';

import { useCameraStore } from '@/stores/useCameraStore';
import {
    LayoutDashboard,
    Camera,
    Activity,
    Database,
    Cpu,
    Thermometer,
    HardDrive
} from 'lucide-react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import type { LucideIcon } from 'lucide-react';
import { cn } from '@/lib/cn';

const navItems = [
    { icon: LayoutDashboard, label: 'Dashboard', href: '/' },
    { icon: Camera, label: 'Cameras', href: '/cameras' },
    { icon: Database, label: 'Persistence', href: '/history' },
];

export default function Sidebar() {
    const pathname = usePathname();
    const systemStatus = useCameraStore((state) => state.systemStatus);

    return (
        <div className="flex flex-col h-screen w-64 bg-slate-900 border-r border-slate-800 text-slate-400">
            <Link href="/" className="p-6 flex items-center gap-3 hover:opacity-80 transition-opacity">
                <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
                    <Activity className="text-white w-5 h-5" />
                </div>
                <span className="text-white font-bold text-lg tracking-tight">VISION AI</span>
            </Link>

            <nav className="flex-1 px-4 space-y-2 mt-4">
                {navItems.map((item) => (
                    <Link
                        key={item.href}
                        href={item.href}
                        className={cn(
                            "flex items-center gap-3 px-3 py-2 rounded-lg transition-all duration-200 group",
                            pathname === item.href
                                ? "bg-blue-600/10 text-blue-400"
                                : "hover:bg-slate-800 hover:text-white"
                        )}
                    >
                        <item.icon className={cn(
                            "w-5 h-5",
                            pathname === item.href ? "text-blue-400" : "group-hover:text-white"
                        )} />
                        <span className="font-medium">{item.label}</span>
                    </Link>
                ))}
            </nav>

            {/* System Status Section */}
            <div className="p-4 bg-slate-950/50 border-t border-slate-800/50 space-y-4">
                <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-widest px-2">Hardware Status</h3>

                <div className="space-y-3 px-2">
                    <StatusItem
                        icon={Cpu}
                        label="GPU Load"
                        value={`${systemStatus?.gpu_util ?? 0}%`}
                        progress={systemStatus?.gpu_util ?? 0}
                        color="bg-blue-500"
                    />
                    <StatusItem
                        icon={Thermometer}
                        label="Temp"
                        value={`${systemStatus?.gpu_temp ?? 0}°C`}
                        progress={(systemStatus?.gpu_temp ?? 0) / 100 * 100}
                        color={systemStatus?.gpu_temp && systemStatus.gpu_temp > 75 ? "bg-red-500" : "bg-emerald-500"}
                    />
                    <StatusItem
                        icon={HardDrive}
                        label="VRAM"
                        value={`${systemStatus?.gpu_mem ?? 0}%`}
                        progress={systemStatus?.gpu_mem ?? 0}
                        color="bg-purple-500"
                    />
                </div>
            </div>
        </div>
    );
}

function StatusItem({
    icon: Icon,
    label,
    value,
    progress,
    color
}: {
    icon: LucideIcon;
    label: string;
    value: string;
    progress: number;
    color: string;
}) {
    return (
        <div className="space-y-1">
            <div className="flex justify-between items-center text-[10px] font-medium uppercase tracking-wider">
                <div className="flex items-center gap-1.5 text-slate-400">
                    <Icon className="w-3 h-3 text-slate-500" />
                    {label}
                </div>
                <span className="text-slate-200" suppressHydrationWarning>{value}</span>
            </div>
            <div className="h-1 w-full bg-slate-800 rounded-full overflow-hidden">
                <div
                    className={cn("h-full transition-all duration-500 ease-out", color)}
                    style={{ width: `${progress}%` }}
                />
            </div>
        </div>
    );
}
