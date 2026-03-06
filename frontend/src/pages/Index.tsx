import { useState, useEffect } from "react";
import { Plus, Activity, Eye, AlertTriangle, Cpu } from "lucide-react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { CameraCard } from "@/components/dashboard/CameraCard";
import { ConnectCameraDialog } from "@/components/dashboard/ConnectCameraDialog";

interface ExtendedSystemStatus {
  ts: number;
  system: {
    cpu_usage: number;
    ram_usage: number;
  };
  gpu?: {
    available: boolean;
    utilization?: number;
  };
}

const Index = () => {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [cameras, setCameras] = useState<string[]>([]);
  const { data: statusData } = useWebSocket<ExtendedSystemStatus>('/ws/status');

  useEffect(() => {
    api.getCameras()
      .then(res => setCameras(Object.keys(res)))
      .catch(err => console.error("Error fetching init cameras:", err));
  }, [dialogOpen]); // Refetch when dialog closes

  const gpuUsage = statusData?.gpu?.available && statusData.gpu.utilization !== undefined
    ? `${statusData.gpu.utilization}%`
    : "N/A";
  const activeFeeds = cameras.length.toString();

  const stats = [
    { label: "Active Feeds", value: activeFeeds, icon: Eye, color: "text-primary" },
    { label: "Detections", value: "---", icon: Activity, color: "text-success" },
    { label: "Alerts", value: "---", icon: AlertTriangle, color: "text-warning" },
    { label: "GPU Usage", value: gpuUsage, icon: Cpu, color: "text-accent" },
  ];
  return (
    <div>
      {/* Header */}
      <div className="flex items-start justify-between mb-8">
        <div>
          <h2 className="text-2xl font-bold text-foreground">
            Good evening, <span className="gradient-text">Operator</span>
          </h2>
          <p className="text-sm text-muted-foreground mt-1">
            {cameras.length} cameras online
          </p>
        </div>
        <Button onClick={() => setDialogOpen(true)} className="gap-2 font-semibold bg-primary text-primary-foreground hover:bg-primary/90 rounded-lg">
          <Plus className="w-4 h-4" />
          Add Camera
        </Button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {stats.map(({ label, value, icon: Icon, color }) => (
          <div key={label} className="glass-card p-4 flex items-center gap-4">
            <div className={`w-10 h-10 rounded-xl bg-muted flex items-center justify-center ${color}`}>
              <Icon className="w-5 h-5" />
            </div>
            <div>
              <p className="text-2xl font-bold text-foreground">{value}</p>
              <p className="text-label">{label}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="mb-4">
        <h3 className="text-sm font-semibold text-foreground tracking-wide">Live Monitors</h3>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
        {cameras.length > 0 ? (
          cameras.map((camId) => (
            <CameraCard key={camId} cameraId={camId} name={camId} />
          ))
        ) : (
          <div className="col-span-full h-40 glass-card flex items-center justify-center text-muted-foreground">
            No cameras active. Add a source to begin monitoring.
          </div>
        )}
      </div>

      <ConnectCameraDialog open={dialogOpen} onOpenChange={setDialogOpen} />
    </div>
  );
};

export default Index;
