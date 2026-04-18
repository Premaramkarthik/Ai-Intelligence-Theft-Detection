import * as React from "react"
import { cn } from "@/utils/cn"

export const Container = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8", className)} {...props} />
  )
)
Container.displayName = "Container"

export interface FlexProps extends React.HTMLAttributes<HTMLDivElement> {
  direction?: "row" | "col"
  align?: "start" | "center" | "end" | "stretch"
  justify?: "start" | "center" | "end" | "between" | "around"
  wrap?: "nowrap" | "wrap" | "wrap-reverse"
  gap?: "0" | "1" | "2" | "3" | "4" | "6" | "8"
}

export const Flex = React.forwardRef<HTMLDivElement, FlexProps>(
  ({ className, direction = "row", align, justify, wrap, gap, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        "flex",
        {
          "flex-col": direction === "col",
          "items-start": align === "start",
          "items-center": align === "center",
          "items-end": align === "end",
          "items-stretch": align === "stretch",
          "justify-start": justify === "start",
          "justify-center": justify === "center",
          "justify-end": justify === "end",
          "justify-between": justify === "between",
          "justify-around": justify === "around",
          "flex-wrap": wrap === "wrap",
          "flex-nowrap": wrap === "nowrap",
          "gap-0": gap === "0",
          "gap-1": gap === "1",
          "gap-2": gap === "2",
          "gap-3": gap === "3",
          "gap-4": gap === "4",
          "gap-6": gap === "6",
          "gap-8": gap === "8",
        },
        className
      )}
      {...props}
    />
  )
)
Flex.displayName = "Flex"

export interface GridProps extends React.HTMLAttributes<HTMLDivElement> {
  cols?: "1" | "2" | "3" | "4" | "6" | "12"
  gap?: "0" | "1" | "2" | "3" | "4" | "6" | "8"
}

export const Grid = React.forwardRef<HTMLDivElement, GridProps>(
  ({ className, cols, gap, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        "grid",
        {
          "grid-cols-1": cols === "1",
          "grid-cols-2": cols === "2",
          "grid-cols-3": cols === "3",
          "grid-cols-4": cols === "4",
          "grid-cols-6": cols === "6",
          "grid-cols-12": cols === "12",
          "gap-0": gap === "0",
          "gap-1": gap === "1",
          "gap-2": gap === "2",
          "gap-3": gap === "3",
          "gap-4": gap === "4",
          "gap-6": gap === "6",
          "gap-8": gap === "8",
        },
        className
      )}
      {...props}
    />
  )
)
Grid.displayName = "Grid"
