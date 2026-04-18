import { StreamCardSkeleton } from "@/components/skeletons/stream-card-skeleton";
import { Skeleton } from "@/components/ui/skeleton";

export function DashboardSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <div
            key={`dashboard-stat-${index}`}
            className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-0)] p-5"
          >
            <Skeleton className="h-3 w-20" />
            <Skeleton className="mt-4 h-8 w-14" />
            <Skeleton className="mt-3 h-3 w-24" />
          </div>
        ))}
      </div>
      <div className="grid gap-5 xl:grid-cols-2">
        {Array.from({ length: 4 }).map((_, index) => (
          <StreamCardSkeleton key={`dashboard-stream-${index}`} />
        ))}
      </div>
    </div>
  );
}

