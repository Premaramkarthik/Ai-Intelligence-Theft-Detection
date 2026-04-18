import { useEffect, useState, useRef, useCallback } from "react"

export type ConnectionState = "connecting" | "connected" | "disconnected" | "error"

export interface FrameData {
  camera_id: string
  stream_name?: string
  width?: number
  height?: number
  preview_jpeg_base64: string | null
  active_tracks?: number
  detections?: number
  timestamp?: string
  // Extend as needed based on CameraFrameKafkaEventPayload
}

export interface InferenceData {
  camera_id: string
  label?: string
  score?: number
  alert_level?: string
  // Extend based on InferenceKafkaEventPayload
}

export interface TrackingTrack {
  track_id: string
  persistent_id: string | null
  class_name: string
  confidence: number
  similarity: number | null
  left: number
  top: number
  width: number
  height: number
}

export interface TrackingData {
  camera_id: string
  tracks: TrackingTrack[]
}

export interface StreamState {
  frames: Record<string, FrameData>
  tracking: Record<string, TrackingData>
  inference: Record<string, InferenceData[]>
}

export function useWebSocket(url: string, cameraId?: string) {
  const [connectionState, setConnectionState] = useState<ConnectionState>("disconnected")
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  
  // We use refs for stream state to prevent triggering massive React re-renders on every 30fps frame.
  // Child video components will pull from this ref or use a custom pub/sub hook.
  const stateRef = useRef<StreamState>({ frames: {}, tracking: {}, inference: {} })
  
  // Handlers for subscribing to specific camera updates
  const subscribersRef = useRef<Set<() => void>>(new Set())

  const subscribe = useCallback((callback: () => void) => {
    subscribersRef.current.add(callback)
    return () => { subscribersRef.current.delete(callback) }
  }, [])

  const notifySubscribers = useCallback(() => {
    subscribersRef.current.forEach(callback => callback())
  }, [])

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    setConnectionState("connecting")
    const wsUrl = cameraId ? `${url}?camera_id=${cameraId}` : url
    
    try {
      const ws = new WebSocket(wsUrl)
      
      ws.onopen = () => {
        setConnectionState("connected")
        if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current)
      }
      
      ws.onmessage = (event) => {
        try {
          const envelope = JSON.parse(event.data)
          const topic = envelope.topic
          const payload = envelope.payload || envelope.message
          
          if (!payload || !payload.camera_id) return
          const cid = payload.camera_id

          if (topic === "camera.frames" || payload.event === "camera.frame") {
            stateRef.current.frames[cid] = payload
            notifySubscribers()
          } else if (topic === "camera.tracking.updates" || payload.event === "tracking.update") {
            stateRef.current.tracking[cid] = payload
            notifySubscribers()
          } else if (topic === "camera.ai_results") {
            if (!stateRef.current.inference[cid]) stateRef.current.inference[cid] = []
            // Keep last 10 inference events
            stateRef.current.inference[cid] = [payload, ...stateRef.current.inference[cid]].slice(0, 10)
            notifySubscribers()
          }
        } catch (e) {
          console.error("Failed to parse websocket message", e)
        }
      }
      
      ws.onclose = () => {
        setConnectionState("disconnected")
        // Exponential backoff or simple fixed backoff
        reconnectTimeoutRef.current = setTimeout(() => connect(), 3000)
      }
      
      ws.onerror = () => {
        setConnectionState("error")
      }
      
      wsRef.current = ws
    } catch (e) {
      setConnectionState("error")
      reconnectTimeoutRef.current = setTimeout(() => connect(), 3000)
    }
  }, [url, cameraId, notifySubscribers])

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current)
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    setConnectionState("disconnected")
  }, [])

  useEffect(() => {
    connect()
    return () => disconnect()
  }, [connect, disconnect])

  return { connectionState, stateRef, subscribe }
}
