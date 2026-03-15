'use client';

import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Camera, Globe, Monitor, Play, X } from 'lucide-react';

import { authHeaders, buildApiUrl, withApiCredentials } from '@/lib/api';
import { getAuthFailureMessage, isAuthFailure } from '@/lib/auth';
import { cn } from '@/lib/cn';
import { useAuthStore } from '@/stores/useAuthStore';
import { useCameraStore } from '@/stores/useCameraStore';
import type { ConnectResponse } from '@/types/contracts';

type SourceType = 'webcam' | 'rtsp';

export default function ConnectionModal({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const token = useAuthStore((state) => state.token);
  const logout = useAuthStore((state) => state.logout);
  const addCamera = useCameraStore((state) => state.addCamera);
  const [sourceType, setSourceType] = useState<SourceType>('rtsp');
  const [formData, setFormData] = useState({
    name: 'Main Entrance',
    store_id: 'main-store',
    rtsp_url: 'rtsp://user:password@192.168.1.100:554/stream1',
  });

  const mutation = useMutation({
    mutationFn: async (data: typeof formData) => {
      const payload =
        sourceType === 'webcam'
          ? {
              source_type: 'webcam',
              store_id: data.store_id.trim() || 'main-store',
            }
          : {
              source_type: 'rtsp',
              store_id: data.store_id.trim() || 'main-store',
              rtsp_config: {
                rtsp_url: data.rtsp_url.trim(),
              },
            };

      const response = await fetch(buildApiUrl('/api/camera/connect'), {
        ...withApiCredentials(),
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
        if (isAuthFailure(response.status, body.detail)) {
          logout();
          throw new Error(getAuthFailureMessage());
        }
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
          url: sourceType === 'webcam' ? 'Webcam 0' : formData.rtsp_url,
          store_id: data.store_id,
          organization_id: data.organization_id,
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
          <InputGroup label="Store ID" icon={Monitor} value={formData.store_id} onChange={(value) => setFormData({ ...formData, store_id: value })} placeholder="main-store" />

          {sourceType === 'rtsp' ? (
            <InputGroup
              label="RTSP URL"
              icon={Globe}
              value={formData.rtsp_url}
              onChange={(value) => setFormData({ ...formData, rtsp_url: value })}
              placeholder="rtsp://user:password@192.168.1.100:554/stream1"
            />
          ) : (
            <div className="space-y-4 rounded-2xl border border-slate-800/50 bg-slate-950/50 p-4">
              <div className="flex items-center gap-3 rounded-xl border border-emerald-500/10 bg-emerald-500/5 p-3 text-emerald-500/80">
                <Monitor className="h-5 w-5" />
                <span className="text-[10px] font-bold uppercase tracking-wider">Using local webcam 0 automatically</span>
              </div>
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
