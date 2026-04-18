import * as React from "react"
import Link from "next/link"
import { cn } from "@/utils/cn"
import { LayoutDashboard, Video, Activity, Settings, List } from "lucide-react"

interface NavItem {
  name: string
  href: string
  icon: React.ElementType
}

const navItems: NavItem[] = [
  { name: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { name: "Cameras", href: "/cameras", icon: Video },
  { name: "Alerts / Logs", href: "/logs", icon: List },
  { name: "Analytics", href: "/analytics", icon: Activity },
  { name: "Settings", href: "/settings", icon: Settings },
]

export function Sidebar({ className }: { className?: string }) {
  return (
    <aside className={cn("hidden md:flex flex-col w-64 border-r border-neutral-800 bg-neutral-950 px-4 py-6", className)}>
      <div className="flex items-center mb-10 px-2 space-x-3">
        <div className="w-8 h-8 rounded-full bg-emerald-500/20 text-emerald-500 flex items-center justify-center">
          <Video size={18} />
        </div>
        <span className="font-semibold text-lg tracking-tight">AI Pipeline</span>
      </div>
      
      <nav className="flex-1 space-y-1">
        {navItems.map((item) => (
          <Link
            key={item.name}
            href={item.href}
            className="flex items-center space-x-3 rounded-md px-3 py-2 text-sm font-medium text-neutral-400 hover:bg-neutral-900 hover:text-white transition-colors"
          >
            <item.icon size={18} className="text-neutral-500" />
            <span>{item.name}</span>
          </Link>
        ))}
      </nav>
      
      <div className="mt-auto pt-6 border-t border-neutral-800">
        <div className="flex items-center space-x-3 px-3">
          <div className="w-8 h-8 rounded-md bg-neutral-800 flex items-center justify-center text-xs">AD</div>
          <div className="flex flex-col">
            <span className="text-sm font-medium text-white">Admin User</span>
            <span className="text-xs text-neutral-500">System Operator</span>
          </div>
        </div>
      </div>
    </aside>
  )
}
