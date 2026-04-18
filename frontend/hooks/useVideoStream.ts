import { useState, useEffect, useRef } from "react"
import type { StreamState } from "./useWebSocket"

/**
 * A lightweight hook to subscribe to a specific camera's data without 
 * linking the entire application to the global WebSocket context.
 */
export function useVideoStream(
  subscribe: (cb: () => void) => () => void,
  stateRef: React.MutableRefObject<StreamState>,
  cameraId: string
) {
  const [frame, setFrame] = useState(stateRef.current.frames[cameraId] || null)
  const [tracking, setTracking] = useState(stateRef.current.tracking[cameraId] || null)
  
  // Throttle state updates using requestAnimationFrame to prevent React thrashing
  const rAFRef = useRef<number | null>(null)

  useEffect(() => {
    const updateState = () => {
      const currentFrame = stateRef.current.frames[cameraId]
      const currentTracking = stateRef.current.tracking[cameraId]
      
      setFrame(currentFrame || null)
      setTracking(currentTracking || null)
    }

    const onWebSocketData = () => {
      if (rAFRef.current === null) {
        rAFRef.current = requestAnimationFrame(() => {
          updateState()
          rAFRef.current = null
        })
      }
    }

    const unsubscribe = subscribe(onWebSocketData)
    return () => {
      unsubscribe()
      if (rAFRef.current !== null) cancelAnimationFrame(rAFRef.current)
    }
  }, [cameraId, stateRef, subscribe])

  return { frame, tracking }
}
