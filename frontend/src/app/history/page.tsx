'use client';

import { useQuery } from '@tanstack/react-query';
import DashboardShell from '@/components/layout/DashboardShell';
import {
    Database,
    Search,
    Filter,
    Calendar,
    Clock,
    Camera as CameraIcon,
    ShieldAlert,
    Download,
    ExternalLink,
    Trash2
} from 'lucide-react';
import { useState } from 'react';
import { cn } from '@/lib/utils';

interface DetectionEvent {
    id: string;
    camera_id: string;
    label: string;
    confidence: number;
    timestamp: string;
    image_path?: string;
    metadata?: any;
}

export default function HistoryPage() {
    const [searchTerm, setSearchTerm] = useState('');
    const [filterLabel, setFilterLabel] = useState('all');

    const { data: events, isLoading } = useQuery<DetectionEvent[]>({
        queryKey: ['history-events'],
        queryFn: async () => {
            const resp = await fetch('http://localhost:9001/api/events');
            if (!resp.ok) throw new Error('Failed to fetch historical events');
            return resp.json();
        }
    });

    const filteredEvents = events?.filter(event => {
        const matchesSearch = event.camera_id.toLowerCase().includes(searchTerm.toLowerCase()) ||
            event.label.toLowerCase().includes(searchTerm.toLowerCase());
        const matchesFilter = filterLabel === 'all' || event.label === filterLabel;
        return matchesSearch && matchesFilter;
    });

    return (
        <DashboardShell>
            <div className="flex flex-col gap-8">
                {/* Header */}
                <div className="flex justify-between items-end">
                    <div>
                        <h1 className="text-3xl font-bold text-white tracking-tight">Forensic History</h1>
                        <p className="text-slate-500 mt-1">Archived detection events and hardware triggers.</p>
                    </div>

                    <div className="flex gap-3">
                        <button className="flex items-center gap-2 bg-slate-800 hover:bg-slate-700 text-slate-200 px-4 py-2 rounded-xl text-sm font-semibold transition-all">
                            <Download className="w-4 h-4" />
                            Export CSV
                        </button>
                    </div>
                </div>

                {/* Filters Bar */}
                <div className="flex flex-wrap gap-4 items-center bg-slate-900/50 p-4 rounded-2xl border border-slate-800">
                    <div className="relative flex-1 min-w-[300px]">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                        <input
                            type="text"
                            placeholder="Search by camera or object..."
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                            className="w-full bg-slate-950 border border-slate-800 rounded-xl py-2 pl-10 pr-4 text-sm text-slate-200 focus:outline-none focus:border-blue-500/50 transition-all"
                        />
                    </div>

                    <div className="flex items-center gap-2 px-3 py-2 bg-slate-950 border border-slate-800 rounded-xl">
                        <Filter className="w-4 h-4 text-slate-500" />
                        <select
                            value={filterLabel}
                            onChange={(e) => setFilterLabel(e.target.value)}
                            className="bg-transparent text-sm text-slate-300 focus:outline-none cursor-pointer"
                        >
                            <option value="all">All Detections</option>
                            <option value="person">Person</option>
                            <option value="shoplifting">Shoplifting (Critical)</option>
                            <option value="weapon">Weapon</option>
                        </select>
                    </div>

                    <div className="flex items-center gap-2 px-3 py-2 bg-slate-950 border border-slate-800 rounded-xl text-sm text-slate-400">
                        <Calendar className="w-4 h-4 text-slate-500" />
                        Last 24 Hours
                    </div>
                </div>

                {/* Events Table / Grid */}
                <div className="bg-slate-900 border border-slate-800 rounded-3xl overflow-hidden shadow-xl">
                    <table className="w-full text-left border-collapse">
                        <thead>
                            <tr className="bg-slate-950/50 text-[10px] uppercase font-bold text-slate-500 tracking-widest border-b border-slate-800">
                                <th className="px-6 py-4">Event Time</th>
                                <th className="px-6 py-4">Source</th>
                                <th className="px-6 py-4">Detection</th>
                                <th className="px-6 py-4">Confidence</th>
                                <th className="px-6 py-4">Status</th>
                                <th className="px-6 py-4 text-right">Actions</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/50">
                            {isLoading ? (
                                <SkeletonRows />
                            ) : filteredEvents && filteredEvents.length > 0 ? (
                                filteredEvents.map((event) => (
                                    <EventRow key={event.id} event={event} />
                                ))
                            ) : (
                                <tr className="hover:bg-slate-800/20 transition-colors">
                                    <td colSpan={6} className="px-6 py-12 text-center text-slate-500 text-sm">
                                        No historical events match your search criteria.
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </DashboardShell>
    );
}

function EventRow({ event }: { event: DetectionEvent }) {
    const date = new Date(event.timestamp);
    const isCritical = event.label === 'shoplifting' || event.label === 'weapon';

    return (
        <tr className="hover:bg-slate-800/20 transition-colors group">
            <td className="px-6 py-4">
                <div className="flex flex-col">
                    <span className="text-sm font-medium text-slate-200" suppressHydrationWarning>{date.toLocaleTimeString()}</span>
                    <span className="text-[10px] text-slate-500" suppressHydrationWarning>{date.toLocaleDateString()}</span>
                </div>
            </td>
            <td className="px-6 py-4">
                <div className="flex items-center gap-2 text-slate-300">
                    <CameraIcon className="w-4 h-4 text-slate-600" />
                    <span className="text-sm font-medium">{event.camera_id}</span>
                </div>
            </td>
            <td className="px-6 py-4">
                <div className={cn(
                    "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold uppercase tracking-wider",
                    isCritical
                        ? "bg-red-500/10 text-red-500 border border-red-500/20"
                        : "bg-blue-500/10 text-blue-400 border border-blue-500/20"
                )}>
                    {isCritical && <ShieldAlert className="w-3.5 h-3.5" />}
                    {event.label}
                </div>
            </td>
            <td className="px-6 py-4">
                <div className="w-24 space-y-1">
                    <div className="flex justify-between text-[10px] font-bold text-slate-500">
                        <span>MATCH</span>
                        <span>{Math.round(event.confidence * 100)}%</span>
                    </div>
                    <div className="h-1 w-full bg-slate-800 rounded-full overflow-hidden">
                        <div
                            className={cn("h-full", event.confidence > 0.8 ? "bg-emerald-500" : "bg-blue-500")}
                            style={{ width: `${event.confidence * 100}%` }}
                        />
                    </div>
                </div>
            </td>
            <td className="px-6 py-4">
                <span className="text-xs font-semibold text-emerald-500 flex items-center gap-1.5">
                    <div className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                    Verified
                </span>
            </td>
            <td className="px-6 py-4 text-right">
                <div className="flex justify-end gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button className="p-2 hover:bg-slate-800 rounded-lg text-slate-500 hover:text-white transition-colors" title="View Details">
                        <ExternalLink className="w-4 h-4" />
                    </button>
                    <button className="p-2 hover:bg-red-500/10 rounded-lg text-slate-500 hover:text-red-500 transition-colors" title="Delete Log">
                        <Trash2 className="w-4 h-4" />
                    </button>
                </div>
            </td>
        </tr>
    );
}

function SkeletonRows() {
    return (
        <>
            {[1, 2, 3, 4, 5].map((i) => (
                <tr key={i}>
                    <td colSpan={6} className="px-6 py-6 font-medium">
                        <div className="h-4 bg-slate-800 rounded w-full animate-pulse" />
                    </td>
                </tr>
            ))}
        </>
    );
}
