import { Badge } from "@/components/ui/badge";
import { Bell, Search, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";

export function TopBar() {
  return (
    <header className="h-16 border-b border-border/50 flex items-center justify-between px-6 backdrop-blur-sm bg-background/80 sticky top-0 z-40">
      <div className="flex items-center gap-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            className="h-9 w-64 rounded-lg bg-muted border-none pl-10 pr-4 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary/50 transition-all"
            placeholder="Search cameras, events..."
          />
        </div>
      </div>
      <div className="flex items-center gap-3">
        <Badge className="border-0 bg-primary/15 text-primary text-[10px] font-semibold tracking-wider uppercase px-2.5 py-1 gap-1.5">
          <Sparkles className="w-3 h-3" />
          AI Active
        </Badge>
        <Button variant="ghost" size="icon" className="relative text-muted-foreground hover:text-foreground">
          <Bell className="w-4 h-4" />
          <span className="absolute top-2 right-2 w-2 h-2 rounded-full bg-primary animate-pulse-glow" />
        </Button>
        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-primary to-accent flex items-center justify-center text-[11px] font-bold text-primary-foreground">
          A
        </div>
      </div>
    </header>
  );
}
