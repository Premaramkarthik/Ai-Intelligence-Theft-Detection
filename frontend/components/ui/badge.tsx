import { cn } from "@/utils/cn";

const toneStyles = {
  neutral: "bg-[var(--surface-1)] text-[var(--text-secondary)]",
  success: "bg-[rgba(38,115,86,0.14)] text-[var(--success-strong)]",
  warning: "bg-[rgba(166,114,53,0.14)] text-[var(--warning-strong)]",
  danger: "bg-[rgba(168,63,53,0.14)] text-[var(--danger-strong)]",
} as const;

export function Badge({
  className,
  tone = "neutral",
  children,
}: {
  className?: string;
  tone?: keyof typeof toneStyles;
  children: React.ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-medium uppercase tracking-[0.14em]",
        toneStyles[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

