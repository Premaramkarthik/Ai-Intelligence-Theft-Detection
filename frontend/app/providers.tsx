"use client";

import { useEffect } from "react";
import { SWRConfig } from "swr";

import { ApiError } from "@/services/apiClient";
import { getRealtimeClient } from "@/services/realtimeClient";

export function Providers({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    const client = getRealtimeClient();
    client.start();
    return () => {
      client.stop();
    };
  }, []);

  return (
    <SWRConfig
      value={{
        revalidateOnFocus: false,
        revalidateOnReconnect: true,
        keepPreviousData: true,
        shouldRetryOnError: (error) => {
          if (error instanceof ApiError) {
            return error.statusCode >= 500 || error.statusCode === 408 || error.statusCode === 429;
          }
          return true;
        },
        errorRetryCount: 2,
      }}
    >
      {children}
    </SWRConfig>
  );
}

