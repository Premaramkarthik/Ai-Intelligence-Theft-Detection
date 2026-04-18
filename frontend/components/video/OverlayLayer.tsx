import * as React from "react"
import { cn } from "@/utils/cn"
import type { TrackingData } from "@/hooks/useWebSocket"

interface OverlayLayerProps {
  tracking: TrackingData | null
  frameWidth?: number
  frameHeight?: number
}

export function OverlayLayer({ tracking, frameWidth = 1920, frameHeight = 1080 }: OverlayLayerProps) {
  if (!tracking || !tracking.tracks || tracking.tracks.length === 0) return null

  return (
    <div className="absolute inset-0 pointer-events-none overflow-hidden">
      {tracking.tracks.map((track) => {
        // Calculate relative positions in percentages based on frame dimensional metadata
        // so the overlay scales dynamically with the <img /> regardless of container size
        const leftPct = (track.left / frameWidth) * 100
        const topPct = (track.top / frameHeight) * 100
        const widthPct = (track.width / frameWidth) * 100
        const heightPct = (track.height / frameHeight) * 100
        
        const label = track.persistent_id || track.track_id

        return (
          <div
            key={track.track_id}
            className="absolute border-2 border-emerald-500 shadow-sm transition-all duration-75 ease-linear"
            style={{
              left: `${leftPct}%`,
              top: `${topPct}%`,
              width: `${widthPct}%`,
              height: `${heightPct}%`,
            }}
          >
            {/* Label Block */}
            <div className="absolute -top-6 left-[-2px] bg-emerald-500 text-neutral-950 font-bold px-1.5 py-0.5 text-[0.65rem] whitespace-nowrap">
              {label} {Math.round(track.confidence * 100)}%
            </div>
          </div>
        )
      })}
    </div>
  )
}
