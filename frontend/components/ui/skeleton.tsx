import { cn } from "@/utils/cn";

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-xl bg-[var(--surface-2)] before:absolute before:inset-0 before:-translate-x-full before:animate-[shimmer_1.6s_infinite] before:bg-[linear-gradient(90deg,transparent,rgba(255,255,255,0.18),transparent)]",
        className,
      )}
    />
  );
}

