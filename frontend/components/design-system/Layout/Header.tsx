import * as React from "react"
import { cn } from "@/utils/cn"
import { Bell, Search } from "lucide-react"

export function Header({ className, title }: { className?: string, title?: string }) {
  return (
    <header className={cn("flex h-16 w-full items-center justify-between border-b border-neutral-800 bg-neutral-950/80 px-6 backdrop-blur-md sticky top-0 z-10", className)}>
      <div className="flex items-center">
        <h1 className="text-lg font-semibold tracking-tight">{title || "Overview"}</h1>
      </div>
      
      <div className="flex items-center space-x-4">
        <div className="relative hidden md:block">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 transform text-neutral-500" size={16} />
          <input
            type="text"
            placeholder="Search cameras..."
            className="h-9 w-64 rounded-full border border-neutral-800 bg-neutral-900/50 pl-10 pr-4 text-sm placeholder:text-neutral-500 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500 transition-colors"
          />
        </div>
        
        <button className="relative flex h-9 w-9 items-center justify-center rounded-full hover:bg-neutral-800 transition-colors">
          <Bell size={18} className="text-neutral-400" />
          <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-red-500"></span>
        </button>
      </div>
    </header>
  )
}
