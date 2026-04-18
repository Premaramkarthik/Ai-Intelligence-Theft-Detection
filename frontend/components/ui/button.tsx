import * as React from "react";

import { cn } from "@/utils/cn";

const buttonVariants = {
  primary:
    "bg-[var(--accent-strong)] text-[var(--surface-0)] hover:bg-[var(--accent-strong-hover)]",
  secondary:
    "border border-[var(--border-strong)] bg-[var(--surface-1)] text-[var(--text-primary)] hover:bg-[var(--surface-2)]",
  ghost:
    "text-[var(--text-secondary)] hover:bg-[var(--surface-1)] hover:text-[var(--text-primary)]",
  danger:
    "border border-[var(--danger-soft)] bg-[rgba(168,63,53,0.12)] text-[var(--danger-strong)] hover:bg-[rgba(168,63,53,0.18)]",
} as const;

type Variant = keyof typeof buttonVariants;

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant = "primary", asChild = false, children, ...props },
  ref,
) {
  const classes = cn(
    "inline-flex h-10 items-center justify-center rounded-xl px-4 text-sm font-medium transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-60",
    buttonVariants[variant],
    className,
  );

  if (asChild && React.isValidElement(children)) {
    const child = children as React.ReactElement<{ className?: string }>;
    return React.cloneElement(child, {
      className: cn(classes, child.props.className),
    });
  }

  return (
    <button
      ref={ref}
      className={classes}
      {...props}
    >
      {children}
    </button>
  );
});
