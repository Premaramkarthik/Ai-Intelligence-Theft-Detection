import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Globe, Monitor, Play, Hash, User, Lock } from "lucide-react";
import { cn } from "@/lib/utils";

type TabType = "rtsp" | "webcam";

interface ConnectCameraDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ConnectCameraDialog({ open, onOpenChange }: ConnectCameraDialogProps) {
  const [tab, setTab] = useState<TabType>("rtsp");
  const [loading, setLoading] = useState(false);

  // Form State
  const [label, setLabel] = useState("");
  const [ipAddress, setIpAddress] = useState("");
  const [port, setPort] = useState("554");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [deviceIndex, setDeviceIndex] = useState("0");

  const handleConnect = async () => {
    setLoading(true);
    try {
      if (tab === "webcam") {
        await api.connectCamera({
          source_type: "webcam",
          device_index: parseInt(deviceIndex, 10),
        });
      } else {
        await api.connectCamera({
          source_type: "rtsp",
          rtsp_config: {
            username,
            password,
            ip_address: ipAddress,
            port: parseInt(port, 10),
            substreams: [label || "main"], // Backend needs at least one substream provided
          },
        });
      }
      toast.success("Camera connected successfully!");
      onOpenChange(false);
    } catch (error: any) {
      toast.error(error.message || "Failed to connect camera");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md bg-card border-border/60 rounded-xl">
        <DialogHeader>
          <DialogTitle className="text-lg font-bold text-foreground">Add Camera</DialogTitle>
        </DialogHeader>

        {/* Tab Toggle */}
        <div className="flex bg-muted rounded-lg p-1">
          {(["rtsp", "webcam"] as TabType[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={cn(
                "flex-1 flex items-center justify-center gap-2 py-2 rounded-md text-xs font-semibold tracking-wider uppercase transition-all",
                tab === t
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              {t === "rtsp" ? <Globe className="w-3.5 h-3.5" /> : <Monitor className="w-3.5 h-3.5" />}
              {t === "rtsp" ? "RTSP" : "Webcam"}
            </button>
          ))}
        </div>

        <div className="space-y-4 mt-2">
          <div>
            <label className="text-label mb-1.5 block">Label</label>
            <div className="relative">
              <Play className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input value={label} onChange={e => setLabel(e.target.value)} className="pl-10 bg-muted border-0 rounded-lg" placeholder="Main Entrance" />
            </div>
          </div>

          {tab === "rtsp" ? (
            <>
              <div className="grid grid-cols-3 gap-3">
                <div className="col-span-2">
                  <label className="text-label mb-1.5 block">IP Address</label>
                  <div className="relative">
                    <Globe className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                    <Input value={ipAddress} onChange={e => setIpAddress(e.target.value)} className="pl-10 bg-muted border-0 rounded-lg" placeholder="192.168.1.100" />
                  </div>
                </div>
                <div>
                  <label className="text-label mb-1.5 block">Port</label>
                  <div className="relative">
                    <Hash className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                    <Input value={port} onChange={e => setPort(e.target.value)} className="pl-10 bg-muted border-0 rounded-lg" placeholder="554" />
                  </div>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-label mb-1.5 block">Username</label>
                  <div className="relative">
                    <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                    <Input value={username} onChange={e => setUsername(e.target.value)} className="pl-10 bg-muted border-0 rounded-lg" placeholder="admin" />
                  </div>
                </div>
                <div>
                  <label className="text-label mb-1.5 block">Password</label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                    <Input value={password} onChange={e => setPassword(e.target.value)} type="password" className="pl-10 bg-muted border-0 rounded-lg" placeholder="••••••" />
                  </div>
                </div>
              </div>
            </>
          ) : (
            <div className="space-y-3">
              <div className="bg-success/10 border border-success/20 rounded-lg px-4 py-3 flex items-center gap-3">
                <Monitor className="w-5 h-5 text-success" />
                <span className="text-xs font-semibold tracking-wider uppercase text-success">Device Ready</span>
              </div>
              <div>
                <label className="text-label mb-1.5 block">Device Index</label>
                <div className="relative">
                  <Hash className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  <Input value={deviceIndex} onChange={e => setDeviceIndex(e.target.value)} type="number" className="pl-10 bg-muted border-0 rounded-lg" placeholder="0" />
                </div>
              </div>
            </div>
          )}

          <Button onClick={handleConnect} disabled={loading} className="w-full font-semibold tracking-wider uppercase rounded-lg" size="lg">
            {loading ? "Connecting..." : "Connect"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
