'use client';

import { useEffect, useRef, useState } from 'react';
import { Maximize2, Activity, ShieldCheck, AlertCircle } from 'lucide-react';
import { CameraSocket, type Detection } from '@/lib/socket';
import { cn } from '@/lib/utils';

interface StreamCardProps {
    id: string;
    name: string;
}

export default function StreamCard({ id, name }: StreamCardProps) {
    const videoRef = useRef<HTMLImageElement>(null);
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const [isLive, setIsLive] = useState(false);

    useEffect(() => {
        const socket = new CameraSocket(`ws://localhost:9001/ws/camera/${id}`, {
            onMessage: (data) => {
                // 1. Update Video Frame (Binary JPEG Blob → Object URL)
                if (data.frame && videoRef.current) {
                    const prevUrl = videoRef.current.src;
                    const url = URL.createObjectURL(data.frame);
                    videoRef.current.src = url;
                    // Revoke previous URL to avoid memory leaks
                    if (prevUrl.startsWith('blob:')) URL.revokeObjectURL(prevUrl);
                    setIsLive(true);
                }

                // 2. Clear and Redraw Canvas Overlays
                if (canvasRef.current) {
                    const ctx = canvasRef.current.getContext('2d');
                    if (!ctx) return;

                    ctx.clearRect(0, 0, canvasRef.current.width, canvasRef.current.height);

                    // Global Action Banner (if any)
                    if (data.action && data.action.label !== 'normal') {
                        ctx.fillStyle = 'rgba(239, 68, 68, 0.8)';
                        ctx.fillRect(0, 0, canvasRef.current.width, 40);
                        ctx.fillStyle = '#FFFFFF';
                        ctx.font = 'bold 20px Inter';
                        ctx.fillText(
                            `TRIGGER: ${data.action.label.toUpperCase()} (${Math.round(data.action.confidence * 100)}%)`,
                            20,
                            28
                        );
                    }

                    // Individual Detections
                    data.detections.forEach((det: Detection) => {
                        const [x1, y1, x2, y2] = det.bbox;
                        const w = x2 - x1;
                        const h = y2 - y1;

                        const isPerson = det.label === 'person';
                        const color = isPerson ? '#3B82F6' : '#F59E0B';

                        ctx.strokeStyle = color;
                        ctx.lineWidth = 3;
                        ctx.setLineDash([]);
                        ctx.strokeRect(x1, y1, w, h);

                        const label = isPerson
                            ? `#${det.track_id?.toString().padStart(2, '0') ?? '??'} PERSON`
                            : det.label.toUpperCase();

                        ctx.fillStyle = color;
                        const textWidth = ctx.measureText(label).width;
                        ctx.fillRect(x1, y1 - 25, textWidth + 15, 25);

                        ctx.fillStyle = '#FFFFFF';
                        ctx.font = 'bold 12px Inter';
                        ctx.fillText(`${label} ${Math.round(det.confidence * 100)}%`, x1 + 7, y1 - 8);
                    });
                }
            },
            onError: (err) => {
                console.error(`Stream ${id} socket error:`, err);
            },
        });

        socket.connect();
        return () => socket.disconnect();
    }, [id]);

    return (
        <div className="group relative bg-slate-900 border border-slate-800 rounded-3xl overflow-hidden shadow-xl transition-all duration-300 hover:border-blue-500/50 hover:shadow-[0_0_30px_-5px_rgba(59,130,246,0.5)]">
            {/* Header */}
            <div className="absolute top-0 inset-x-0 p-4 z-10 flex justify-between items-center bg-gradient-to-b from-slate-950/80 to-transparent">
                <div className="flex items-center gap-2">
                    <div className={cn(
                        "w-2 h-2 rounded-full",
                        isLive ? "bg-emerald-500 animate-pulse" : "bg-slate-600"
                    )} />
                    <span className="text-xs font-bold text-white tracking-wide uppercase opacity-90">{name}</span>
                </div>
                <button className="p-1.5 bg-slate-950/40 hover:bg-slate-800 rounded-lg text-slate-400 hover:text-white transition-colors">
                    <Maximize2 className="w-4 h-4" />
                </button>
            </div>

            {/* Media Content */}
            <div className="relative aspect-video bg-slate-950 flex items-center justify-center">
                {!isLive && (
                    <div className="flex flex-col items-center gap-3 text-slate-700">
                        <Activity className="w-10 h-10 animate-pulse" />
                        <span className="text-[10px] font-bold uppercase tracking-[0.2em]">Initiating Handshake</span>
                    </div>
                )}

                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                    ref={videoRef}
                    className="absolute inset-0 w-full h-full object-cover"
                    alt={name}
                />

                <canvas
                    ref={canvasRef}
                    width={1280}
                    height={720}
                    className="absolute inset-0 w-full h-full pointer-events-none"
                />
            </div>

            {/* Footer / Stats */}
            <div className="p-4 flex items-center justify-between bg-slate-900/50">
                <div className="flex items-center gap-4">
                    <div className="flex flex-col">
                        <span className="text-[9px] font-bold text-slate-500 uppercase tracking-tighter">AI Inference</span>
                        <span className="text-xs font-medium text-slate-300">YOLO 2.6 Staged</span>
                    </div>
                    <div className="h-6 w-px bg-slate-800" />
                    <div className="flex flex-col">
                        <span className="text-[9px] font-bold text-slate-500 uppercase tracking-tighter">Status</span>
                        <span className="text-xs font-medium text-emerald-500">OPTIMAL</span>
                    </div>
                </div>

                <div className="flex gap-2">
                    <ShieldCheck className="w-5 h-5 text-blue-500/50" />
                    <AlertCircle className="w-5 h-5 text-slate-700" />
                </div>
            </div>
        </div>
    );
}
