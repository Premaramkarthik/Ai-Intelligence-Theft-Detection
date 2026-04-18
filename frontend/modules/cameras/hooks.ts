"use client";

import useSWR from "swr";
import { useMemo } from "react";

import * as cameraApi from "@/modules/cameras/api";

export function useCameraList(params?: Parameters<typeof cameraApi.listCameras>[0]) {
  const key = useMemo(() => ["cameras", params ?? {}] as const, [params]);
  return useSWR(key, () => cameraApi.listCameras(params));
}

export function useCamera(cameraId: string | null | undefined) {
  return useSWR(cameraId ? ["camera", cameraId] : null, () => cameraApi.getCamera(cameraId as string));
}

