import { cn } from "@/utils/cn";

export function EmptyState({
  title,
  description,
  className,
}: {
  title: string;
  description: string;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex min-h-56 flex-col items-center justify-center rounded-2xl border border-dashed border-[var(--border-strong)] bg-[var(--surface-1)] px-6 text-center",
        className,
      )}
    >
      <h3 className="text-base font-semibold text-[var(--text-primary)]">{title}</h3>
      <p className="mt-2 max-w-xl text-sm text-[var(--text-secondary)]">{description}</p>
    </div>
  );
}

