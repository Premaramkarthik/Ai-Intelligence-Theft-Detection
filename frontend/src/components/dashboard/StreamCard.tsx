'use client';

import { useEffect, useRef, useState } from 'react';
import { Activity, AlertCircle, Maximize2, ShieldCheck } from 'lucide-react';

import { buildWsUrl } from '@/lib/api';
import { cn } from '@/lib/cn';
import { useAuthStore } from '@/stores/useAuthStore';

interface Detection {
  bbox: number[];
  label: string;
  confidence: number;
  track_id?: string | number | null;
}

interface Incident {
  label: string;
  confidence: number;
  severity: string;
}

interface CameraStreamMessage {
  message_type: 'camera.stream';
  camera_id: string;
  timestamp: string;
  image_jpeg_base64: string;
  detections: Detection[];
  incident: Incident | null;
}

interface StreamCardProps {
  id: string;
  name: string;
}

export default function StreamCard({ id, name }: StreamCardProps) {
  const token = useAuthStore((state) => state.token);
  const imageRef = useRef<HTMLImageElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [isLive, setIsLive] = useState(false);
  const [incident, setIncident] = useState<Incident | null>(null);

  useEffect(() => {
    if (!token) {
      return;
    }

    const socket = new WebSocket(buildWsUrl(`/ws/camera/${id}`, token));
    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as CameraStreamMessage;
        if (data.message_type !== 'camera.stream') {
          return;
        }
        if (imageRef.current) {
          imageRef.current.src = `data:image/jpeg;base64,${data.image_jpeg_base64}`;
        }
        drawDetections(data.detections, data.incident, canvasRef.current);
        setIncident(data.incident);
        setIsLive(true);
      } catch (err) {
        console.error(`Failed to parse camera stream for ${id}`, err);
      }
    };
    socket.onclose = () => setIsLive(false);
    socket.onerror = () => setIsLive(false);
    return () => socket.close();
  }, [id, token]);

  return (
    <div className="group relative overflow-hidden rounded-3xl border border-slate-800 bg-slate-900 shadow-xl transition-all duration-300 hover:border-blue-500/50 hover:shadow-[0_0_30px_-5px_rgba(59,130,246,0.5)]">
      <div className="absolute inset-x-0 top-0 z-10 flex items-center justify-between bg-gradient-to-b from-slate-950/80 to-transparent p-4">
        <div className="flex items-center gap-2">
          <div className={cn('h-2 w-2 rounded-full', isLive ? 'bg-emerald-500 animate-pulse' : 'bg-slate-600')} />
          <span className="text-xs font-bold uppercase tracking-wide text-white/90">{name}</span>
        </div>
        <button className="rounded-lg bg-slate-950/40 p-1.5 text-slate-400 transition-colors hover:bg-slate-800 hover:text-white">
          <Maximize2 className="h-4 w-4" />
        </button>
      </div>

      <div className="relative aspect-video bg-slate-950">
        {!isLive ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-slate-700">
            <Activity className="h-10 w-10 animate-pulse" />
            <span className="text-[10px] font-bold uppercase tracking-[0.2em]">Waiting for backend stream</span>
          </div>
        ) : null}

        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img ref={imageRef} className="absolute inset-0 h-full w-full object-cover" alt={name} />
        <canvas ref={canvasRef} width={1280} height={720} className="absolute inset-0 h-full w-full pointer-events-none" />
      </div>

      <div className="flex items-center justify-between bg-slate-900/50 p-4">
        <div className="flex items-center gap-4">
          <div className="flex flex-col">
            <span className="text-[9px] font-bold uppercase tracking-tighter text-slate-500">Protocol</span>
            <span className="text-xs font-medium text-slate-300">Authenticated WS JSON</span>
          </div>
          <div className="h-6 w-px bg-slate-800" />
          <div className="flex flex-col">
            <span className="text-[9px] font-bold uppercase tracking-tighter text-slate-500">Incident</span>
            <span className={cn('text-xs font-medium', incident ? 'text-red-400' : 'text-emerald-500')}>
              {incident ? incident.label.toUpperCase() : isLive ? 'CLEAR' : 'OFFLINE'}
            </span>
          </div>
        </div>

        <div className="flex gap-2">
          <ShieldCheck className="h-5 w-5 text-blue-500/50" />
          <AlertCircle className={cn('h-5 w-5', incident ? 'text-red-400' : 'text-slate-700')} />
        </div>
      </div>
    </div>
  );
}

function drawDetections(detections: Detection[], incident: Incident | null, canvas: HTMLCanvasElement | null) {
  if (!canvas) {
    return;
  }
  const ctx = canvas.getContext('2d');
  if (!ctx) {
    return;
  }
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  if (incident) {
    ctx.fillStyle = 'rgba(239, 68, 68, 0.8)';
    ctx.fillRect(0, 0, canvas.width, 40);
    ctx.fillStyle = '#FFFFFF';
    ctx.font = 'bold 20px sans-serif';
    ctx.fillText(`INCIDENT: ${incident.label.toUpperCase()} (${Math.round(incident.confidence * 100)}%)`, 20, 28);
  }

  ctx.font = 'bold 12px sans-serif';
  detections.forEach((det) => {
    const [x1, y1, x2, y2] = det.bbox;
    const width = x2 - x1;
    const height = y2 - y1;
    const isPerson = det.label === 'person';
    const color = isPerson ? '#3B82F6' : '#F59E0B';
    const tag = isPerson ? `PERSON ${det.track_id ?? ''}`.trim() : det.label.toUpperCase();

    ctx.strokeStyle = color;
    ctx.lineWidth = 3;
    ctx.strokeRect(x1, y1, width, height);

    const text = `${tag} ${Math.round(det.confidence * 100)}%`;
    const textWidth = ctx.measureText(text).width;
    ctx.fillStyle = color;
    ctx.fillRect(x1, Math.max(y1 - 24, 0), textWidth + 14, 24);
    ctx.fillStyle = '#FFFFFF';
    ctx.fillText(text, x1 + 7, Math.max(y1 - 8, 12));
  });
}
