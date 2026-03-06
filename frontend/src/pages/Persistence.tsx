import { useEffect, useState } from "react";
import { Download, Search, Filter, Clock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";

interface EventRecord {
  camera_id: string;
  trace_id: string;
  label: string;
  confidence: number;
  created_at: string;
}

const Persistence = () => {
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchEvents = async () => {
      try {
        const data = await api.getEvents(50);
        setEvents(data);
      } catch (err) {
        toast.error("Failed to load historical events");
      } finally {
        setLoading(false);
      }
    };
    fetchEvents();
  }, []);

  return (
    <div>
      <div className="flex items-start justify-between mb-8">
        <div>
          <h2 className="text-2xl font-bold text-foreground">Event History</h2>
          <p className="text-sm text-muted-foreground mt-1">
            Browse and export past detection events.
          </p>
        </div>
        <Button variant="outline" className="gap-2 font-semibold rounded-lg">
          <Download className="w-4 h-4" />
          Export
        </Button>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3 mb-5">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input className="pl-10 bg-muted border-0 rounded-lg" placeholder="Search events..." />
        </div>
        <Button variant="outline" size="sm" className="gap-2 rounded-lg">
          <Filter className="w-3.5 h-3.5" />
          Filter
        </Button>
        <Button variant="outline" size="sm" className="gap-2 rounded-lg">
          <Clock className="w-3.5 h-3.5" />
          Last 24h
        </Button>
      </div>

      <div className="space-y-2">
        {loading ? (
          <p className="text-muted-foreground p-4">Loading events...</p>
        ) : events.length === 0 ? (
          <p className="text-muted-foreground p-4">No events found.</p>
        ) : (
          events.map((event, i) => (
            <div
              key={event.trace_id || i}
              className="glass-card px-5 py-3.5 flex items-center gap-6 hover:border-primary/20 transition-all duration-200 cursor-pointer"
            >
              <span className="text-xs font-mono text-muted-foreground w-16">
                {new Date(event.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
              </span>
              <span className="text-sm text-foreground font-medium w-28 truncate">{event.camera_id}</span>
              <span className="text-sm text-foreground w-20">{event.label}</span>
              <div className="flex items-center gap-2 w-24">
                <div className="h-1.5 flex-1 rounded-full bg-muted overflow-hidden">
                  <div
                    className="h-full rounded-full bg-primary"
                    style={{ width: `${event.confidence * 100}%` }}
                  />
                </div>
                <span className="text-[11px] font-mono text-muted-foreground">{(event.confidence * 100).toFixed(0)}%</span>
              </div>
              <span className={cn(
                "text-[10px] font-semibold tracking-wider uppercase px-2 py-0.5 rounded-md",
                event.confidence > 0.8 ? "bg-success/15 text-success" : "bg-warning/15 text-warning"
              )}>
                {event.confidence > 0.8 ? "confirmed" : "review"}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default Persistence;
