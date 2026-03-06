import { Sliders, Palette, Bell, Shield, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

const sections = [
  { icon: Sliders, label: "Inference Engine", desc: "GPU allocation, model selection, confidence thresholds", color: "text-primary" },
  { icon: Shield, label: "Security & Access", desc: "API keys, authentication, role management", color: "text-success" },
  { icon: Bell, label: "Notifications", desc: "Alert channels, escalation rules, schedules", color: "text-warning" },
  { icon: Palette, label: "Appearance", desc: "Theme, layout density, dashboard widgets", color: "text-accent" },
];

const SettingsPage = () => {
  return (
    <div>
      <div className="mb-8">
        <h2 className="text-2xl font-bold text-foreground">Settings</h2>
        <p className="text-sm text-muted-foreground mt-1">
          Configure your Vision AI deployment.
        </p>
      </div>

      <div className="space-y-2 max-w-2xl">
        {sections.map(({ icon: Icon, label, desc, color }) => (
          <button
            key={label}
            className="glass-card w-full px-5 py-4 flex items-center gap-4 text-left hover:border-primary/30 transition-all duration-200 group"
          >
            <div className={cn("w-10 h-10 rounded-xl bg-muted flex items-center justify-center", color)}>
              <Icon className="w-5 h-5" />
            </div>
            <div className="flex-1">
              <h3 className="text-sm font-semibold text-foreground">{label}</h3>
              <p className="text-xs text-muted-foreground mt-0.5">{desc}</p>
            </div>
            <ChevronRight className="w-4 h-4 text-muted-foreground group-hover:text-foreground transition-colors" />
          </button>
        ))}
      </div>

      <div className="mt-8 text-center">
        <p className="text-[10px] tracking-[0.3em] uppercase text-muted-foreground/40 font-mono">
          VISION AI · v2.1.0 · Build 4092
        </p>
      </div>
    </div>
  );
};

export default SettingsPage;
