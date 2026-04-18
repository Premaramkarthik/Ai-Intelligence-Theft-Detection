import { Skeleton } from "@/components/ui/skeleton";

export function StreamCardSkeleton() {
  return (
    <div className="overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-0)]">
      <div className="flex items-center justify-between border-b border-[var(--border-subtle)] px-4 py-3">
        <div className="space-y-2">
          <Skeleton className="h-3 w-16" />
          <Skeleton className="h-4 w-32" />
        </div>
        <Skeleton className="h-7 w-20 rounded-full" />
      </div>
      <div className="p-4">
        <Skeleton className="aspect-video w-full rounded-2xl" />
        <div className="mt-4 grid grid-cols-3 gap-3">
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
        </div>
      </div>
    </div>
  );
}

