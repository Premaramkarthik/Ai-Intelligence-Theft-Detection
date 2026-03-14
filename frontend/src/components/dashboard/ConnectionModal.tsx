'use client';

import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Camera, Globe, Hash, Lock, Monitor, Play, User, X } from 'lucide-react';

import { authHeaders, buildApiUrl } from '@/lib/api';
import { cn } from '@/lib/cn';
import { useAuthStore } from '@/stores/useAuthStore';
import { useCameraStore } from '@/stores/useCameraStore';

type SourceType = 'webcam' | 'rtsp';

interface ConnectResponse {
  status: string;
  message: string;
  stream_ids: string[];
}

export default function ConnectionModal({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const token = useAuthStore((state) => state.token);
  const addCamera = useCameraStore((state) => state.addCamera);
  const [sourceType, setSourceType] = useState<SourceType>('rtsp');
  const [formData, setFormData] = useState({
    name: 'Main Entrance',
    device_index: '0',
    ip: '192.168.1.100',
    port: '554',
    username: '',
    password: '',
    substream: 'stream1',
  });

  const mutation = useMutation({
    mutationFn: async (data: typeof formData) => {
      const payload =
        sourceType === 'webcam'
          ? {
              source_type: 'webcam',
              device_index: Number.parseInt(data.device_index, 10) || 0,
            }
          : {
              source_type: 'rtsp',
              rtsp_config: {
                username: data.username,
                password: data.password,
                ip_address: data.ip,
                port: Number.parseInt(data.port, 10) || 554,
                substreams: [data.substream],
              },
            };

      const response = await fetch(buildApiUrl('/api/camera/connect'), {
        method: 'POST',
        headers: {
          ...Object.fromEntries(authHeaders({ token }).entries()),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });
      const body = (await response.json().catch(() => ({ detail: 'Source connection refused' }))) as ConnectResponse & {
        detail?: string;
      };
      if (!response.ok) {
        throw new Error(body.detail ?? 'Connection failed');
      }
      return body;
    },
    onSuccess: (data) => {
      const cameraId = data.stream_ids[0];
      if (cameraId) {
        addCamera({
          id: cameraId,
          name: formData.name,
          url: sourceType === 'webcam' ? `Webcam ${formData.device_index}` : formData.ip,
          status: 'online',
        });
      }
      onClose();
    },
  });

  if (!isOpen) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-slate-950/80 backdrop-blur-sm" onClick={onClose} />

      <div className="relative w-full max-w-md overflow-hidden rounded-3xl border border-slate-800 bg-slate-900 shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-800 p-6">
          <h2 className="text-xl font-bold tracking-tight text-white">System Onboarding</h2>
          <button onClick={onClose} className="rounded-full p-2 transition-colors hover:bg-slate-800">
            <X className="h-5 w-5 text-slate-500" />
          </button>
        </div>

        <div className="px-6 pt-6">
          <div className="flex rounded-xl border border-slate-800/50 bg-slate-950 p-1">
            <button
              onClick={() => setSourceType('rtsp')}
              className={cn(
                'flex flex-1 items-center justify-center gap-2 rounded-lg py-2 text-xs font-bold transition-all',
                sourceType === 'rtsp' ? 'bg-slate-800 text-blue-400 shadow-sm' : 'text-slate-500 hover:text-slate-300',
              )}
            >
              <Globe className="h-3.5 w-3.5" />
              RTSP NETWORK
            </button>
            <button
              onClick={() => setSourceType('webcam')}
              className={cn(
                'flex flex-1 items-center justify-center gap-2 rounded-lg py-2 text-xs font-bold transition-all',
                sourceType === 'webcam' ? 'bg-slate-800 text-blue-400 shadow-sm' : 'text-slate-500 hover:text-slate-300',
              )}
            >
              <Camera className="h-3.5 w-3.5" />
              LOCAL WEBCAM
            </button>
          </div>
        </div>

        <form
          onSubmit={(event) => {
            event.preventDefault();
            mutation.mutate(formData);
          }}
          className="space-y-4 p-6"
        >
          <InputGroup label="Dashboard Label" icon={Play} value={formData.name} onChange={(value) => setFormData({ ...formData, name: value })} placeholder="Security Zone A" />

          {sourceType === 'rtsp' ? (
            <>
              <div className="grid grid-cols-3 gap-4">
                <div className="col-span-2">
                  <InputGroup label="IP Address" icon={Globe} value={formData.ip} onChange={(value) => setFormData({ ...formData, ip: value })} placeholder="10.0.0.5" />
                </div>
                <InputGroup label="Port" icon={Hash} value={formData.port} onChange={(value) => setFormData({ ...formData, port: value })} placeholder="554" />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <InputGroup label="Username" icon={User} value={formData.username} onChange={(value) => setFormData({ ...formData, username: value })} placeholder="operator" />
                <InputGroup label="Password" icon={Lock} type="password" value={formData.password} onChange={(value) => setFormData({ ...formData, password: value })} placeholder="••••••" />
              </div>

              <InputGroup label="Substream Identifier" icon={Hash} value={formData.substream} onChange={(value) => setFormData({ ...formData, substream: value })} placeholder="stream1" />
            </>
          ) : (
            <div className="space-y-4 rounded-2xl border border-slate-800/50 bg-slate-950/50 p-4">
              <div className="flex items-center gap-3 rounded-xl border border-emerald-500/10 bg-emerald-500/5 p-3 text-emerald-500/80">
                <Monitor className="h-5 w-5" />
                <span className="text-[10px] font-bold uppercase tracking-wider">Internal bus ready</span>
              </div>
              <InputGroup label="Hardware Device Index" icon={Hash} value={formData.device_index} onChange={(value) => setFormData({ ...formData, device_index: value })} placeholder="0" />
            </div>
          )}

          {mutation.isError ? (
            <div className="rounded-xl border border-red-500/10 bg-red-500/5 p-3 text-[10px] font-bold uppercase tracking-tight text-red-400">
              Source Error: {mutation.error.message}
            </div>
          ) : null}

          <button
            type="submit"
            disabled={mutation.isPending || !token}
            className="mt-4 flex w-full items-center justify-center gap-2 rounded-2xl bg-blue-600 py-3.5 font-bold text-white transition-all shadow-lg shadow-blue-900/20 active:scale-[0.98] disabled:bg-blue-600/50"
          >
            {mutation.isPending ? 'INITIALIZING...' : 'ESTABLISH CONNECTION'}
          </button>
        </form>
      </div>
    </div>
  );
}

function InputGroup({
  label,
  icon: Icon,
  value,
  onChange,
  type = 'text',
  placeholder,
}: {
  label: string;
  icon: typeof Camera;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  placeholder: string;
}) {
  return (
    <div className="space-y-1.5">
      <label className="ml-1 text-[10px] font-bold uppercase tracking-wider text-slate-500">{label}</label>
      <div className="relative">
        <Icon className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-600" />
        <input
          type={type}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          className="w-full rounded-xl border border-slate-800 bg-slate-950 py-3 pl-11 pr-4 text-sm text-slate-200 transition-all placeholder:text-slate-700 focus:border-blue-500/50 focus:outline-none focus:ring-1 focus:ring-blue-500/20"
        />
      </div>
    </div>
  );
}
