import { LayoutDashboard, Camera, Database, Settings, Cpu, Thermometer, MemoryStick, Zap } from "lucide-react";
import { NavLink, useLocation } from "react-router-dom";
import { cn } from "@/lib/utils";

const navItems = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/cameras", label: "Cameras", icon: Camera },
  { to: "/persistence", label: "History", icon: Database },
  { to: "/settings", label: "Settings", icon: Settings },
];

const hardwareStats = [
  { label: "GPU", value: "12%", icon: Cpu, color: "text-primary" },
  { label: "TEMP", value: "42°C", icon: Thermometer, color: "text-success" },
  { label: "RAM", value: "3.2G", icon: MemoryStick, color: "text-accent" },
];

export function AppSidebar() {
  const location = useLocation();

  return (
    <aside className="fixed left-0 top-0 bottom-0 w-[220px] bg-sidebar flex flex-col z-50">
      {/* Logo */}
      <div className="flex items-center gap-3 px-5 h-16">
        <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-primary to-accent flex items-center justify-center shadow-lg">
          <Zap className="w-4 h-4 text-primary-foreground" />
        </div>
        <div>
          <span className="font-bold text-foreground text-sm tracking-tight block">VISION AI</span>
          <span className="text-[10px] text-muted-foreground font-mono">v2.1.0</span>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-2 space-y-0.5">
        <p className="text-label px-3 mb-2 mt-2">NAVIGATION</p>
        {navItems.map(({ to, label, icon: Icon }) => {
          const isActive = location.pathname === to;
          return (
            <NavLink
              key={to}
              to={to}
              className={cn(
                "flex items-center gap-3 px-3 py-2.5 rounded-lg text-[13px] font-medium transition-all duration-200",
                isActive
                  ? "bg-primary/10 text-primary glow-amber"
                  : "text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
              )}
            >
              <Icon className={cn("w-4 h-4", isActive && "text-primary")} />
              {label}
              {isActive && (
                <div className="ml-auto w-1.5 h-1.5 rounded-full bg-primary animate-pulse-glow" />
              )}
            </NavLink>
          );
        })}
      </nav>

      {/* Hardware Status */}
      <div className="px-4 pb-5">
        <div className="glass-card p-3">
          <p className="text-label mb-3">SYSTEM LOAD</p>
          <div className="space-y-2.5">
            {hardwareStats.map(({ label, value, icon: Icon, color }) => (
              <div key={label} className="flex items-center justify-between">
                <span className="flex items-center gap-2 text-[11px] text-sidebar-muted">
                  <Icon className={cn("w-3.5 h-3.5", color)} />
                  {label}
                </span>
                <span className="text-[11px] text-foreground font-mono font-medium">{value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </aside>
  );
}
