'use client';

import { FormEvent, useState } from 'react';
import { Shield, User, Lock } from 'lucide-react';

import { buildApiUrl } from '@/lib/api';
import { cn } from '@/lib/cn';
import { useAuthStore } from '@/stores/useAuthStore';

export default function AuthPanel() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const setToken = useAuthStore((state) => state.setToken);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      const body = new URLSearchParams();
      body.set('username', username);
      body.set('password', password);
      const response = await fetch(buildApiUrl('/auth/token'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: body.toString(),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail ?? 'Authentication failed');
      }
      setToken(payload.access_token);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Authentication failed');
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center p-6">
      <div className="w-full max-w-md rounded-3xl border border-slate-800 bg-slate-900/80 shadow-2xl overflow-hidden">
        <div className="border-b border-slate-800 p-8">
          <div className="flex items-center gap-3 text-blue-400">
            <Shield className="h-7 w-7" />
            <div>
              <h1 className="text-2xl font-bold text-white">Secure Access Required</h1>
              <p className="mt-1 text-sm text-slate-400">Streaming, history, and camera mutation routes now require a valid token.</p>
            </div>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5 p-8">
          <Field
            icon={User}
            label="Username"
            value={username}
            onChange={setUsername}
            autoComplete="username"
          />
          <Field
            icon={Lock}
            label="Password"
            type="password"
            value={password}
            onChange={setPassword}
            autoComplete="current-password"
          />

          {error ? (
            <div className="rounded-2xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
              {error}
            </div>
          ) : null}

          <button
            type="submit"
            disabled={pending}
            className={cn(
              'w-full rounded-2xl px-4 py-3 text-sm font-semibold text-white transition-colors',
              pending ? 'bg-blue-700/70' : 'bg-blue-600 hover:bg-blue-500',
            )}
          >
            {pending ? 'Signing in...' : 'Sign in'}
          </button>
        </form>
      </div>
    </div>
  );
}

function Field({
  icon: Icon,
  label,
  type = 'text',
  value,
  onChange,
  autoComplete,
}: {
  icon: typeof User;
  label: string;
  type?: string;
  value: string;
  onChange: (value: string) => void;
  autoComplete: string;
}) {
  return (
    <label className="block space-y-2">
      <span className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">{label}</span>
      <div className="relative">
        <Icon className="absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-600" />
        <input
          type={type}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          autoComplete={autoComplete}
          className="w-full rounded-2xl border border-slate-800 bg-slate-950 py-3 pl-11 pr-4 text-sm text-slate-100 outline-none transition-colors focus:border-blue-500/50"
        />
      </div>
    </label>
  );
}
