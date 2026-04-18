import { Skeleton } from "@/components/ui/skeleton";

export function CameraTableSkeleton() {
  return (
    <div className="overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-0)]">
      <div className="border-b border-[var(--border-subtle)] px-5 py-4">
        <Skeleton className="h-4 w-40" />
      </div>
      <div className="space-y-3 p-5">
        {Array.from({ length: 6 }).map((_, index) => (
          <div
            key={`camera-row-${index}`}
            className="grid gap-4 rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-1)] p-4 lg:grid-cols-[1.6fr_1.3fr_1fr_1fr]"
          >
            <div className="space-y-2">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-3 w-40" />
            </div>
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-8 w-28 rounded-full" />
            <div className="flex gap-2">
              <Skeleton className="h-9 w-20 rounded-xl" />
              <Skeleton className="h-9 w-20 rounded-xl" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

