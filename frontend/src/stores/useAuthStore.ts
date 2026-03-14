'use client';

import { create } from 'zustand';

const TOKEN_KEY = 'pipeline_auth_token';

interface AuthState {
  token: string | null;
  hydrated: boolean;
  setToken: (token: string | null) => void;
  hydrate: () => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  hydrated: false,
  setToken: (token) => {
    if (typeof window !== 'undefined') {
      if (token) {
        window.localStorage.setItem(TOKEN_KEY, token);
      } else {
        window.localStorage.removeItem(TOKEN_KEY);
      }
    }
    set({ token });
  },
  hydrate: () => {
    if (typeof window === 'undefined') {
      set({ hydrated: true });
      return;
    }
    set({
      token: window.localStorage.getItem(TOKEN_KEY),
      hydrated: true,
    });
  },
  logout: () => {
    if (typeof window !== 'undefined') {
      window.localStorage.removeItem(TOKEN_KEY);
    }
    set({ token: null });
  },
}));
