import * as React from "react"
import { AppLayout } from "@/components/shared/AppLayout"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/design-system/Core/Card"
import { Grid } from "@/components/design-system/Layout/Primitives"

export default function AnalyticsPage() {
  return (
    <AppLayout title="Analytics Dashboard">
      <div className="w-full max-w-7xl mx-auto space-y-6 animate-in">
        <Grid cols="3" gap="6">
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-sm font-medium text-neutral-500">Total Detections (24h)</CardTitle></CardHeader>
            <CardContent className="text-3xl font-semibold">12,504</CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-sm font-medium text-neutral-500">Unique Identities tracked</CardTitle></CardHeader>
            <CardContent className="text-3xl font-semibold text-emerald-500">342</CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-sm font-medium text-neutral-500">Pipeline Latency Average</CardTitle></CardHeader>
            <CardContent className="text-3xl font-semibold">41.2 ms</CardContent>
          </Card>
        </Grid>
        
        <Card className="h-64 flex items-center justify-center border-dashed border-neutral-800 bg-transparent">
          <p className="text-neutral-500">Historical chart component placeholder</p>
        </Card>
      </div>
    </AppLayout>
  )
}
