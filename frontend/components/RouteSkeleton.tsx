interface RouteSkeletonProps {
  variant: "dashboard" | "camera";
}

/**
 * Render animated loading placeholders for the main App Router screens.
 */
export function RouteSkeleton({ variant }: RouteSkeletonProps) {
  const detailBlocks =
    variant === "dashboard"
      ? Array.from({ length: 6 }, (_, index) => `dashboard-${index}`)
      : Array.from({ length: 3 }, (_, index) => `camera-${index}`);

  return (
    <section className="screen-enter space-y-6">
      <div className="space-y-3">
        <div className="skeleton-block h-4 w-32 rounded-full" />
        <div className="skeleton-block h-12 w-80 max-w-full rounded-2xl" />
        <div className="skeleton-block h-5 w-[32rem] max-w-full rounded-full" />
      </div>
      <div
        className={
          variant === "dashboard"
            ? "grid gap-5 md:grid-cols-2 xl:grid-cols-3"
            : "grid gap-6 xl:grid-cols-[minmax(0,1.6fr)_minmax(340px,0.9fr)]"
        }
      >
        {detailBlocks.map((block) => (
          <div
            key={block}
            className="skeleton-block min-h-56 rounded-[28px] border border-white/8 bg-slate-800/70"
          />
        ))}
      </div>
    </section>
  );
}
