"use client"

import * as React from "react"
import { useEffect, useState } from "react"
import { AppLayout } from "@/components/shared/AppLayout"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/design-system/Core/Card"
import { Button } from "@/components/design-system/Core/Button"
import { Input } from "@/components/design-system/Core/Input"
import { Badge } from "@/components/design-system/Core/Badge"
import { fetchApi } from "@/utils/api"
import { Loader } from "@/components/design-system/Core/Loader"

export default function SettingsPage() {
  const [health, setHealth] = useState<any>(null)
  
  useEffect(() => {
    async function loadHealth() {
      try {
        const data = await fetchApi<any>("/health")
        setHealth(data)
      } catch(err) {
        console.error(err)
      }
    }
    loadHealth()
    
    // Auto refresh health every 15 seconds
    const interval = setInterval(loadHealth, 15000)
    return () => clearInterval(interval)
  }, [])
  
  const getBadgeVariant = (s?: string) => s === "ok" ? "success" : s === "error" ? "error" : "warning"

  return (
    <AppLayout title="System Settings">
      <div className="w-full max-w-5xl mx-auto space-y-6 animate-in">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Global Inference Settings</CardTitle>
                <p className="text-xs text-neutral-500 mt-1">Configure global tolerances and detection parameters</p>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium text-neutral-300">Confidence Threshold</label>
                  <Input type="number" defaultValue={0.65} step={0.05} min={0} max={1} className="w-32" />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium text-neutral-300">Identity Retention (Hours)</label>
                  <Input type="number" defaultValue={24} className="w-32" />
                </div>
                <div className="pt-2">
                  <Button variant="primary">Save Changes</Button>
                </div>
              </CardContent>
            </Card>
          </div>

          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>System Health</CardTitle>
              </CardHeader>
              <CardContent>
                {!health ? (
                  <div className="flex items-center text-neutral-500"><Loader size="sm" className="mr-2"/> Fetching status...</div>
                ) : (
                  <div className="space-y-4">
                    <div className="flex justify-between items-center text-sm border-b border-neutral-800 pb-2">
                      <span className="text-neutral-400">Uptime</span>
                      <span className="text-neutral-300 font-mono">{(health.uptime_seconds / 3600).toFixed(2)} hrs</span>
                    </div>
                    <div className="flex justify-between items-center text-sm">
                      <span className="text-neutral-400" title={health.components?.database?.message}>Database</span>
                      <Badge variant={getBadgeVariant(health.components?.database?.status)}>
                        {health.components?.database?.status?.toUpperCase() || "UNKNOWN"}
                      </Badge>
                    </div>
                    <div className="flex justify-between items-center text-sm">
                      <span className="text-neutral-400" title={health.components?.tracking_kafka_producer?.message}>Tracking Kafka</span>
                      <Badge variant={getBadgeVariant(health.components?.tracking_kafka_producer?.status)}>
                        {health.components?.tracking_kafka_producer?.status?.toUpperCase() || "UNKNOWN"}
                      </Badge>
                    </div>
                    <div className="flex justify-between items-center text-sm">
                      <span className="text-neutral-400" title={health.components?.stream_event_consumer?.message}>Stream Consumer</span>
                      <Badge variant={getBadgeVariant(health.components?.stream_event_consumer?.status)}>
                        {health.components?.stream_event_consumer?.status?.toUpperCase() || "UNKNOWN"}
                      </Badge>
                    </div>
                    <div className="flex justify-between items-center text-sm">
                      <span className="text-neutral-400" title={health.components?.inference_manager?.message}>Inference Manager</span>
                      <Badge variant={getBadgeVariant(health.components?.inference_manager?.status)}>
                         {health.components?.inference_manager?.status?.toUpperCase() || "UNKNOWN"}
                      </Badge>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </AppLayout>
  )
}
