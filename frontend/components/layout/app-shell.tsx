"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, Camera, LayoutGrid, Settings } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/utils/cn";
import { useRealtimeOverview } from "@/hooks/useRealtime";

const navigation = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutGrid },
  { href: "/cameras", label: "Cameras", icon: Camera },
  { href: "/analytics", label: "Analytics", icon: Activity },
  { href: "/settings", label: "Settings", icon: Settings },
];

function connectionTone(state: string) {
  if (state === "connected") {
    return "success" as const;
  }
  if (state === "reconnecting" || state === "connecting") {
    return "warning" as const;
  }
  return "danger" as const;
}

export function AppShell({
  title,
  description,
  children,
  actions,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
  actions?: React.ReactNode;
}) {
  const pathname = usePathname();
  const realtime = useRealtimeOverview();

  return (
    <div className="grid min-h-screen gap-6 lg:grid-cols-[240px_minmax(0,1fr)]">
      <aside className="rounded-[28px] border border-[var(--border-subtle)] bg-[var(--surface-0)] p-5 shadow-[0_24px_72px_rgba(16,24,32,0.08)]">
        <div className="border-b border-[var(--border-subtle)] pb-5">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-[var(--text-muted)]">
            Sentinel Deck
          </p>
          <h1 className="mt-3 text-xl font-semibold text-[var(--text-primary)]">
            Vision Operations
          </h1>
          <p className="mt-2 text-sm text-[var(--text-secondary)]">
            Minimal live monitoring for streams, tracking, and inference.
          </p>
        </div>

        <nav className="mt-5 space-y-1.5">
          {navigation.map((item) => {
            const Icon = item.icon;
            const active = pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-3 rounded-2xl px-3 py-3 text-sm font-medium transition-colors",
                  active
                    ? "bg-[var(--accent-quiet)] text-[var(--text-primary)]"
                    : "text-[var(--text-secondary)] hover:bg-[var(--surface-1)] hover:text-[var(--text-primary)]",
                )}
              >
                <Icon className="h-4 w-4" />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="mt-8 rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-1)] p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--text-muted)]">
            Realtime status
          </p>
          <div className="mt-3 flex items-center justify-between">
            <span className="text-sm text-[var(--text-secondary)]">Event bus</span>
            <Badge tone={connectionTone(realtime.connectionState)}>
              {realtime.connectionState}
            </Badge>
          </div>
          <p className="mt-3 text-xs text-[var(--text-secondary)]">
            {realtime.lastMessageAt
              ? `Last message ${new Date(realtime.lastMessageAt).toLocaleTimeString()}`
              : "Waiting for the first websocket event."}
          </p>
        </div>
      </aside>

      <div className="min-w-0">
        <header className="rounded-[28px] border border-[var(--border-subtle)] bg-[var(--surface-0)] px-6 py-5 shadow-[0_24px_72px_rgba(16,24,32,0.08)]">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-[var(--text-muted)]">
                Operations Console
              </p>
              <h2 className="mt-2 text-3xl font-semibold tracking-tight text-[var(--text-primary)]">
                {title}
              </h2>
              {description ? (
                <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--text-secondary)]">
                  {description}
                </p>
              ) : null}
            </div>
            {actions ? <div className="flex flex-wrap gap-3">{actions}</div> : null}
          </div>
        </header>

        <main className="mt-6 space-y-6">{children}</main>
      </div>
    </div>
  );
}

