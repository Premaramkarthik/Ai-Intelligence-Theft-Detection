import { Skeleton } from "@/components/ui/skeleton";

export function CameraDetailSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid gap-4 lg:grid-cols-[1.6fr_minmax(0,0.9fr)]">
        <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-0)] p-5">
          <Skeleton className="h-5 w-40" />
          <Skeleton className="mt-4 aspect-video w-full rounded-2xl" />
        </div>
        <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-0)] p-5">
          <Skeleton className="h-5 w-24" />
          <div className="mt-4 space-y-3">
            {Array.from({ length: 5 }).map((_, index) => (
              <Skeleton key={`camera-detail-${index}`} className="h-12 w-full" />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

