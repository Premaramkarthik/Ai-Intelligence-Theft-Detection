import { useEffect, useState } from "react";
import { Camera as CameraIcon, Settings2, Wifi, WifiOff, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { toast } from "sonner";

const Cameras = () => {
  const [cameraIds, setCameraIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchCameras = async () => {
    try {
      const res = await api.getCameras();
      setCameraIds(Object.keys(res));
    } catch (err) {
      toast.error("Failed to load camera fleet");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCameras();
  }, []);

  const handleRemove = async (camId: string) => {
    try {
      await api.removeCamera(camId);
      toast.success(`${camId} removed`);
      fetchCameras();
    } catch (err) {
      toast.error(`Failed to remove ${camId}`);
    }
  };

  return (
    <div>
      <div className="mb-8">
        <h2 className="text-2xl font-bold text-foreground">Camera Fleet</h2>
        <p className="text-sm text-muted-foreground mt-1">
          Manage connected devices and inference configurations.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {loading ? (
          <p className="text-muted-foreground p-4">Loading fleet...</p>
        ) : cameraIds.length === 0 ? (
          <p className="text-muted-foreground p-4">No cameras connected. Add one from the dashboard.</p>
        ) : (
          cameraIds.map((camId) => (
            <div key={camId} className="glass-card p-5 flex items-center gap-5 group hover:border-primary/30 transition-all duration-200">
              <div className="w-12 h-12 rounded-xl flex items-center justify-center bg-primary/10 text-primary">
                <CameraIcon className="w-5 h-5" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <h3 className="font-semibold text-foreground text-sm">{camId}</h3>
                  <Wifi className="w-3.5 h-3.5 text-success" />
                </div>
                <div className="flex gap-4 text-[11px] text-muted-foreground">
                  <span className="font-mono">Active</span>
                </div>
              </div>
              <button
                onClick={() => handleRemove(camId)}
                className="p-2 rounded-lg hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-all opacity-0 group-hover:opacity-100"
                title="Remove Camera"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default Cameras;
