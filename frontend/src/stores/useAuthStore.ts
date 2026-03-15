'use client';

import { create } from 'zustand';

import { buildApiUrl, withApiCredentials } from '@/lib/api';

const COOKIE_SESSION_TOKEN = 'cookie';

interface AuthState {
  token: string | null;
  hydrated: boolean;
  setToken: (token: string | null) => void;
  hydrate: () => Promise<void>;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  hydrated: false,
  setToken: (token) => {
    set({ token: token ? COOKIE_SESSION_TOKEN : null, hydrated: true });
  },
  hydrate: async () => {
    if (typeof window === 'undefined') {
      set({ hydrated: true });
      return;
    }

    try {
      const response = await fetch(buildApiUrl('/auth/session'), withApiCredentials());
      if (!response.ok) {
        set({ token: null, hydrated: true });
        return;
      }
      set({ token: COOKIE_SESSION_TOKEN, hydrated: true });
    } catch {
      set({ token: null, hydrated: true });
    }
  },
  logout: () => {
    if (typeof window !== 'undefined') {
      void fetch(buildApiUrl('/auth/logout'), withApiCredentials({ method: 'POST' })).catch(() => undefined);
    }
    set({ token: null });
  },
}));
