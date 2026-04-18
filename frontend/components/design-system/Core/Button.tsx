import * as React from "react"
import { cn } from "@/utils/cn"

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "danger" | "ghost"
  size?: "sm" | "md" | "lg"
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "primary", size = "md", ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(
          "inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium transition-colors",
          "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-emerald-500 disabled:pointer-events-none disabled:opacity-50",
          {
            "bg-emerald-600 text-white hover:bg-emerald-700 shadow-sm": variant === "primary",
            "bg-neutral-800 text-neutral-100 hover:bg-neutral-700 border border-neutral-700 shadow-sm": variant === "secondary",
            "bg-red-500/10 text-red-500 hover:bg-red-500/20": variant === "danger",
            "hover:bg-neutral-800 hover:text-neutral-100 text-neutral-400": variant === "ghost",
            "h-8 px-3 text-xs": size === "sm",
            "h-9 px-4": size === "md",
            "h-10 px-8": size === "lg",
          },
          className
        )}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"
