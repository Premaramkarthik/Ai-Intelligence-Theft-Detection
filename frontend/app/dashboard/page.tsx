"use client"

import * as React from "react"
import { useEffect, useState } from "react"
import { AppLayout } from "@/components/shared/AppLayout"
import { useWebSocket } from "@/hooks/useWebSocket"
import { LiveVideoPlayer } from "@/components/video/LiveVideoPlayer"
import { Grid, Flex } from "@/components/design-system/Layout/Primitives"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/design-system/Core/Card"
import { Badge } from "@/components/design-system/Core/Badge"
import { fetchApi } from "@/utils/api"

export default function DashboardPage() {
  const wsUrl = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/streams/ws/updates"
  const { connectionState, stateRef, subscribe } = useWebSocket(wsUrl)
  
  const [activeCameras, setActiveCameras] = useState<any[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [dashboardMetrics, setDashboardMetrics] = useState({ latency: 0, alerts_recent: [] })
  
  useEffect(() => {
    async function loadCameras() {
      try {
        const data = await fetchApi<any>("/cameras")
        // Data might be paginated { items: [], total: x } or just an array
        const camerasList = Array.isArray(data) ? data : (data.items || [])
        // Filter only active cameras for the dashboard
        setActiveCameras(camerasList.filter((c: any) => c.status === "active"))
      } catch (err) {
        console.error("Failed to fetch cameras:", err)
      } finally {
        setIsLoading(false)
      }
    }
    loadCameras()
  }, [])

  return (
    <AppLayout title="Live Dashboard">
      <Flex direction="col" gap="6" className="w-full h-full max-w-7xl mx-auto">
        
        {/* Status Bar */}
        <Flex justify="between" align="center" className="w-full bg-neutral-900/40 p-3 rounded-lg border border-neutral-800">
          <div className="flex items-center space-x-3">
            <h2 className="text-sm font-medium text-neutral-300">Connection Status</h2>
            <Badge 
              variant={connectionState === "connected" ? "success" : connectionState === "connecting" ? "warning" : "error"}
            >
              {connectionState.toUpperCase()}
            </Badge>
          </div>
          <div className="text-sm text-neutral-500 font-mono">
            {isLoading ? "Loading..." : `${activeCameras.length} Active Feeds`}
          </div>
        </Flex>
        
        {/* Main Camera Grid */}
        {isLoading ? (
          <div className="flex items-center justify-center p-12 text-neutral-500">Loading feeds...</div>
        ) : activeCameras.length === 0 ? (
          <div className="flex flex-col items-center justify-center p-12 text-neutral-500 bg-neutral-900/20 border border-neutral-800 border-dashed rounded-lg">
            <p>No active cameras found.</p>
            <p className="text-xs mt-2">Go to the Cameras page to add or activate streams.</p>
          </div>
        ) : (
          <Grid cols="2" gap="4" className="w-full">
            {activeCameras.map((cam) => (
              <LiveVideoPlayer
                key={cam.id}
                cameraId={cam.id}
                cameraName={cam.name}
                stateRef={stateRef}
                subscribe={subscribe}
                className="w-full h-[320px]"
              />
            ))}
          </Grid>
        )}

        {/* Dynamic Analytics Panel (Bound to WebSocket state/API) */}
        <Grid cols="4" gap="4" className="w-full mt-2">
          <Card>
            <CardHeader className="p-4 pb-2">
              <CardTitle className="text-xs text-neutral-500 font-medium">System Health</CardTitle>
            </CardHeader>
            <CardContent className="p-4 pt-0 text-xl font-semibold flex items-center justify-between">
              <span>Operational</span>
              <div className="h-3 w-3 bg-emerald-500 rounded-full animate-pulse shadow-[0_0_8px_rgba(16,185,129,0.5)]"></div>
            </CardContent>
          </Card>
          
          <Card>
            <CardHeader className="p-4 pb-2">
              <CardTitle className="text-xs text-neutral-500 font-medium">Registered Cameras</CardTitle>
            </CardHeader>
            <CardContent className="p-4 pt-0 text-2xl font-semibold text-emerald-500">
               {isLoading ? "-" : activeCameras.length}
            </CardContent>
          </Card>
          
          <Card className="col-span-2 relative overflow-hidden group">
            <CardHeader className="p-4 pb-2 border-b border-neutral-800">
              <CardTitle className="text-xs text-neutral-500 font-medium">Recent Stream Activity (Live)</CardTitle>
            </CardHeader>
            <CardContent className="p-0 flex flex-col h-24 overflow-hidden relative">
               <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(16,185,129,0.03),transparent_50%)] pointer-events-none"></div>
               <div className="flex flex-col text-sm divide-y divide-neutral-800/50 flex-1 overflow-y-auto w-full p-2">
                  <div className="p-2 text-neutral-400 flex justify-between items-center text-xs">
                     <span className="flex items-center gap-2"><span className="w-1.5 h-1.5 bg-neutral-600 rounded-full"></span> Subscribed to websocket event bus.</span>
                     <span>Waiting for inference alerts...</span>
                  </div>
               </div>
            </CardContent>
          </Card>
        </Grid>
        
      </Flex>
    </AppLayout>
  )
}

