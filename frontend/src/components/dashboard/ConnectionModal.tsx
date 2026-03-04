'use client';

import { useState } from 'react';
import { X, Globe, User, Lock, Hash, Play, Monitor, Camera } from 'lucide-react';
import { useMutation } from '@tanstack/react-query';
import { useCameraStore } from '@/stores/useCameraStore';
import { cn } from '@/lib/utils';

type SourceType = 'webcam' | 'rtsp';

export default function ConnectionModal({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
    const [sourceType, setSourceType] = useState<SourceType>('rtsp');
    const [formData, setFormData] = useState({
        name: 'Main Entrance',
        device_index: '0',
        ip: '192.168.1.100',
        port: '554',
        username: 'admin',
        password: '',
        substream: 'stream1'
    });

    const addCamera = useCameraStore((state) => state.addCamera);

    const mutation = useMutation({
        mutationFn: async (data: typeof formData) => {
            const payload = sourceType === 'webcam'
                ? {
                    source_type: 'webcam',
                    device_index: parseInt(data.device_index) || 0
                }
                : {
                    source_type: 'rtsp',
                    rtsp_config: {
                        username: data.username,
                        password: data.password,
                        ip_address: data.ip,
                        port: parseInt(data.port) || 554,
                        substreams: [data.substream]
                    }
                };

            const resp = await fetch('http://localhost:9001/api/camera/connect', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (!resp.ok) {
                const err = await resp.json().catch(() => ({ detail: 'Source connection refused' }));
                throw new Error(err.detail || 'Connection failed');
            }
            return resp.json();
        },
        onSuccess: (data) => {
            // Backend returns stream_ids as a list
            const cameraId = data.stream_ids?.[0];
            if (cameraId) {
                addCamera({
                    id: cameraId,
                    name: formData.name,
                    url: sourceType === 'webcam' ? `Webcam ${formData.device_index}` : formData.ip,
                    status: 'online'
                });
            }
            onClose();
        }
    });

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <div className="absolute inset-0 bg-slate-950/80 backdrop-blur-sm" onClick={onClose} />

            <div className="relative w-full max-w-md bg-slate-900 border border-slate-800 rounded-3xl shadow-2xl overflow-hidden animate-in fade-in zoom-in duration-200">
                <div className="p-6 border-b border-slate-800 flex justify-between items-center">
                    <h2 className="text-xl font-bold text-white tracking-tight">System Onboarding</h2>
                    <button onClick={onClose} className="p-2 hover:bg-slate-800 rounded-full transition-colors">
                        <X className="w-5 h-5 text-slate-500" />
                    </button>
                </div>

                {/* Source Switcher */}
                <div className="px-6 pt-6">
                    <div className="flex bg-slate-950 p-1 rounded-xl border border-slate-800/50">
                        <button
                            onClick={() => setSourceType('rtsp')}
                            className={cn(
                                "flex-1 flex items-center justify-center gap-2 py-2 rounded-lg text-xs font-bold transition-all",
                                sourceType === 'rtsp' ? "bg-slate-800 text-blue-400 shadow-sm" : "text-slate-500 hover:text-slate-300"
                            )}
                        >
                            <Globe className="w-3.5 h-3.5" />
                            RTSP NETWORK
                        </button>
                        <button
                            onClick={() => setSourceType('webcam')}
                            className={cn(
                                "flex-1 flex items-center justify-center gap-2 py-2 rounded-lg text-xs font-bold transition-all",
                                sourceType === 'webcam' ? "bg-slate-800 text-blue-400 shadow-sm" : "text-slate-500 hover:text-slate-300"
                            )}
                        >
                            <Camera className="w-3.5 h-3.5" />
                            LOCAL WEBCAM
                        </button>
                    </div>
                </div>

                <form onSubmit={(e) => { e.preventDefault(); mutation.mutate(formData); }} className="p-6 space-y-4">
                    <InputGroup label="Dashboard Label" icon={Play} value={formData.name} onChange={(v: string) => setFormData({ ...formData, name: v })} placeholder="Security Zone A" />

                    {sourceType === 'rtsp' ? (
                        <>
                            <div className="grid grid-cols-3 gap-4">
                                <div className="col-span-2">
                                    <InputGroup label="IP Address" icon={Globe} value={formData.ip} onChange={(v: string) => setFormData({ ...formData, ip: v })} placeholder="10.0.0.5" />
                                </div>
                                <InputGroup label="Port" icon={Hash} value={formData.port} onChange={(v: string) => setFormData({ ...formData, port: v })} placeholder="554" />
                            </div>

                            <div className="grid grid-cols-2 gap-4">
                                <InputGroup label="Username" icon={User} value={formData.username} onChange={(v: string) => setFormData({ ...formData, username: v })} placeholder="admin" />
                                <InputGroup label="Password" icon={Lock} type="password" value={formData.password} onChange={(v: string) => setFormData({ ...formData, password: v })} placeholder="••••••" />
                            </div>

                            <InputGroup label="Substream Identifier" icon={Hash} value={formData.substream} onChange={(v: string) => setFormData({ ...formData, substream: v })} placeholder="stream1" />
                        </>
                    ) : (
                        <div className="bg-slate-950/50 border border-slate-800/50 p-4 rounded-2xl space-y-4">
                            <div className="flex items-center gap-3 text-emerald-500/80 bg-emerald-500/5 p-3 rounded-xl border border-emerald-500/10">
                                <Monitor className="w-5 h-5" />
                                <span className="text-[10px] font-bold uppercase tracking-wider">Internal Bus Ready</span>
                            </div>
                            <InputGroup label="Hardware Device Index" icon={Hash} value={formData.device_index} onChange={(v: string) => setFormData({ ...formData, device_index: v })} placeholder="0" />
                            <p className="px-2 text-[10px] text-slate-500 leading-relaxed italic">
                                Connect a local USB or Integrated camera. Device index '0' is usually the default system camera.
                            </p>
                        </div>
                    )}

                    {mutation.isError && (
                        <div className="flex items-center gap-2 p-3 bg-red-500/5 border border-red-500/10 rounded-xl">
                            <div className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
                            <p className="text-red-400 text-[10px] font-bold uppercase tracking-tight">Source Error: {mutation.error.message}</p>
                        </div>
                    )}

                    <button
                        type="submit"
                        disabled={mutation.isPending}
                        className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-blue-600/50 text-white font-bold py-3.5 rounded-2xl transition-all active:scale-[0.98] mt-4 flex items-center justify-center gap-2 shadow-lg shadow-blue-900/20"
                    >
                        {mutation.isPending ? (
                            <>
                                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                                INITIALIZING...
                            </>
                        ) : (
                            'ESTABLISH CONNECTION'
                        )}
                    </button>
                </form>
            </div>
        </div>
    );
}

function InputGroup({ label, icon: Icon, value, onChange, type = "text", placeholder }: any) {
    return (
        <div className="space-y-1.5">
            <label className="text-[10px] uppercase font-bold text-slate-500 tracking-wider ml-1">{label}</label>
            <div className="relative">
                <Icon className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-600" />
                <input
                    type={type}
                    value={value}
                    onChange={e => onChange(e.target.value)}
                    placeholder={placeholder}
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl py-3 pl-11 pr-4 text-sm text-slate-200 focus:outline-none focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/20 transition-all placeholder:text-slate-700"
                />
            </div>
        </div>
    );
}
