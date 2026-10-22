import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-[3px] text-[10.5px] font-medium tracking-[0.04em]",
  {
    variants: {
      variant: {
        default: "border-accent-400/30 bg-accent-400/10 text-accent-200",
        secondary: "border-white/10 bg-white/[0.045] text-mist-300",
        success: "border-jade-400/30 bg-jade-400/[0.09] text-jade-400",
        warning: "border-amber-400/30 bg-amber-400/[0.09] text-amber-400",
        danger: "border-crimson-400/30 bg-crimson-400/[0.09] text-crimson-400",
        info: "border-cyan-400/25 bg-cyan-400/[0.08] text-cyan-300",
        outline: "border-white/15 text-mist-400",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

const DOT_TONES: Record<NonNullable<BadgeProps["variant"]>, string> = {
  default: "bg-accent-400",
  secondary: "bg-mist-500",
  success: "bg-jade-400",
  warning: "bg-amber-400",
  danger: "bg-crimson-400",
  info: "bg-cyan-400",
  outline: "bg-mist-600",
};

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {
  /** Render a small leading status dot in the matching tone. */
  dot?: boolean;
}

function Badge({ className, variant = "default", dot = false, children, ...props }: BadgeProps) {
  return (
    <span data-slot="badge" className={cn(badgeVariants({ variant }), className)} {...props}>
      {dot ? (
        <span className={cn("status-dot", DOT_TONES[variant ?? "default"])} aria-hidden />
      ) : null}
      {children}
    </span>
  );
}

export { Badge, badgeVariants };
