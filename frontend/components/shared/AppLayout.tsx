import * as React from "react"
import { Sidebar } from "../design-system/Layout/Sidebar"
import { Header } from "../design-system/Layout/Header"

export function AppLayout({ children, title }: { children: React.ReactNode, title?: string }) {
  return (
    <div className="flex h-screen overflow-hidden bg-bg-primary text-text-primary">
      {/* Persistent Sidebar */}
      <Sidebar />
      
      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden relative">
        <Header title={title} />
        
        <main className="flex-1 overflow-y-auto p-4 md:p-6 lg:p-8">
          {children}
        </main>
      </div>
    </div>
  )
}
