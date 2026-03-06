import { useEffect, useRef, useState } from "react";
import { Maximize2, Shield, MoreVertical } from "lucide-react";
import { cn } from "@/lib/utils";

interface CameraCardProps {
  cameraId: string;
  name: string;
}

export function CameraCard({ cameraId, name }: CameraCardProps) {
  const [status, setStatus] = useState<"OPTIMAL" | "WARNING" | "OFFLINE">("OFFLINE");
  const [model, setModel] = useState<string>("Loading...");
  const [imgUrl, setImgUrl] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    // We connect to the WebSocket endpoint for the specific camera
    const ws = new WebSocket(`ws://localhost:9001/ws/camera/${cameraId}`);
    ws.binaryType = "blob"; // Expect binary JPEG frames
    wsRef.current = ws;

    ws.onopen = () => setStatus("OPTIMAL");

    ws.onmessage = (event) => {
      // The backend sends alternating binary (JPEG) and text (metadata) frames, or sometimes just binary depending on the implementation
      // Wait, backend says: "await websocket.send_bytes(jpeg) ... await websocket.send_text(json)"
      if (event.data instanceof Blob) {
        if (imgUrl) URL.revokeObjectURL(imgUrl);
        const url = URL.createObjectURL(event.data);
        setImgUrl(url);
      } else if (typeof event.data === "string") {
        try {
          const metadata = JSON.parse(event.data);
          // E.g., we could update detections/alerts from metadata here
          setModel(metadata.action || "Active");
        } catch (e) { }
      }
    };

    ws.onclose = () => setStatus("OFFLINE");

    return () => {
      ws.close();
      if (imgUrl) URL.revokeObjectURL(imgUrl);
    };
  }, [cameraId]);
  const statusConfig = {
    OPTIMAL: { color: "text-success", bg: "bg-success/15", dot: "bg-success" },
    WARNING: { color: "text-warning", bg: "bg-warning/15", dot: "bg-warning" },
    OFFLINE: { color: "text-destructive", bg: "bg-destructive/15", dot: "bg-destructive" },
  }[status];

  return (
    <div className="glass-card overflow-hidden group transition-all duration-300 hover:border-primary/30 hover:glow-amber">
      {/* Video area */}
      <div className="relative bg-gradient-to-br from-muted/50 to-muted/20 aspect-video flex items-center justify-center">
        <div className="absolute top-3 left-3 flex items-center gap-2">
          <span className={cn("w-2 h-2 rounded-full animate-pulse-glow", statusConfig.dot)} />
          <span className="text-[11px] font-semibold tracking-wider uppercase text-foreground/90">{name}</span>
        </div>
        <button className="absolute top-3 right-3 text-muted-foreground hover:text-foreground transition-colors opacity-0 group-hover:opacity-100">
          <Maximize2 className="w-4 h-4" />
        </button>

        {imgUrl ? (
          <img src={imgUrl} alt={name} className="absolute inset-0 w-full h-full object-cover" />
        ) : (
          <div className="flex flex-col items-center gap-3 text-muted-foreground z-10">
            <div className="flex items-end gap-[3px] h-8">
              {[3, 5, 4, 7, 3, 6, 4, 5, 3, 7, 5, 4].map((h, i) => (
                <div
                  key={i}
                  className="w-[3px] bg-primary/30 rounded-full animate-pulse-glow"
                  style={{ height: `${h * 3}px`, animationDelay: `${i * 0.15}s` }}
                />
              ))}
            </div>
            <span className="text-[10px] tracking-[0.25em] uppercase font-mono text-muted-foreground/60">
              {status === "OFFLINE" ? "Offline" : "Awaiting Signal"}
            </span>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between px-4 py-3">
        <div className="flex gap-5">
          <div>
            <p className="text-label text-[9px] mb-0.5">MODEL</p>
            <p className="text-xs font-medium text-foreground">{model}</p>
          </div>
          <div>
            <p className="text-label text-[9px] mb-0.5">STATUS</p>
            <span className={cn("text-xs font-semibold inline-flex items-center gap-1.5", statusConfig.color)}>
              {status}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <button className="p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-success transition-all"><Shield className="w-3.5 h-3.5" /></button>
          <button className="p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-all"><MoreVertical className="w-3.5 h-3.5" /></button>
        </div>
      </div>
    </div>
  );
}
