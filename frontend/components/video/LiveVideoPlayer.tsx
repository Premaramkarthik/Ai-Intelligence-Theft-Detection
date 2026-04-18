import * as React from "react"
import { cn } from "@/utils/cn"
import { useVideoStream } from "@/hooks/useVideoStream"
import type { StreamState } from "@/hooks/useWebSocket"
import { OverlayLayer } from "./OverlayLayer"
import { Loader } from "@/components/design-system/Core/Loader"
import { Badge } from "@/components/design-system/Core/Badge"

interface LiveVideoPlayerProps {
  cameraId: string
  cameraName?: string
  subscribe: (cb: () => void) => () => void
  stateRef: React.MutableRefObject<StreamState>
  className?: string
}

export const LiveVideoPlayer = React.memo(({
  cameraId,
  cameraName,
  subscribe,
  stateRef,
  className
}: LiveVideoPlayerProps) => {
  const { frame, tracking } = useVideoStream(subscribe, stateRef, cameraId)
  
  return (
    <div className={cn("relative flex flex-col group rounded-lg overflow-hidden border border-neutral-800 bg-neutral-900", className)}>
      {/* Top Header Overlay */}
      <div className="absolute top-0 left-0 w-full z-10 p-3 bg-gradient-to-b from-black/80 to-transparent flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <Badge variant="success" className="animate-pulse shadow-sm shadow-emerald-500/20 px-1.5 rounded-sm !py-0.5 !text-[0.6rem] flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse block"></span>
            LIVE
          </Badge>
          <span className="text-xs font-semibold drop-shadow-md text-white tracking-wide">
            {cameraName || cameraId}
          </span>
        </div>
      </div>

      {/* Video Content */}
      <div className="relative w-full aspect-video bg-neutral-950 flex items-center justify-center">
        {!frame?.preview_jpeg_base64 ? (
          <div className="flex flex-col items-center justify-center text-neutral-500 space-y-3">
            <Loader size="md" />
            <span className="text-xs font-medium uppercase tracking-wider">Awaiting Stream...</span>
          </div>
        ) : (
          <>
            <img
              src={`data:image/jpeg;base64,${frame.preview_jpeg_base64}`}
              alt={`Live view ${cameraId}`}
              className="absolute inset-0 w-full h-full object-contain"
            />
            {/* Inference / Bounding Box Overlay */}
            <OverlayLayer tracking={tracking} frameWidth={frame.width || 1280} frameHeight={frame.height || 720} />
          </>
        )}
      </div>

      {/* Bottom Telemetry Overlay */}
      <div className="absolute bottom-0 left-0 w-full z-10 p-2 bg-gradient-to-t from-black/90 to-transparent flex items-center justify-between opacity-0 group-hover:opacity-100 transition-opacity duration-300">
        <div className="text-[0.65rem] text-neutral-300 flex space-x-3 font-mono">
          <span title="Pipeline Latency">Lat: {frame?.pipeline_latency_ms ? `${frame.pipeline_latency_ms.toFixed(1)}ms` : "N/A"}</span>
          <span title="Active Tracks">Tracks: {frame?.active_tracks ?? 0}</span>
          <span title="Motion" className={cn({ "text-warning": frame?.motion?.foreground_ratio && frame.motion.foreground_ratio > 0.1 })}>
            Motion: {frame?.motion?.foreground_ratio ? `${(frame.motion.foreground_ratio * 100).toFixed(1)}%` : "0%"}
          </span>
        </div>
        <div className="text-[0.65rem] text-neutral-500 font-mono">
          {frame?.sequence_number ? `#${frame.sequence_number}` : ""}
        </div>
      </div>
    </div>
  )
})
LiveVideoPlayer.displayName = "LiveVideoPlayer"
