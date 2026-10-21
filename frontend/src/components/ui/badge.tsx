import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-[11px] font-medium tracking-[0.04em]",
  {
    variants: {
      variant: {
        default: "border-gold-400/30 bg-gold-400/10 text-gold-200",
        secondary: "border-white/10 bg-white/[0.04] text-mist-300",
        success: "border-jade-400/30 bg-jade-400/10 text-jade-400",
        warning: "border-amber-400/30 bg-amber-400/10 text-amber-400",
        danger: "border-crimson-400/30 bg-crimson-400/10 text-crimson-400",
        outline: "border-white/15 text-mist-300",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <span data-slot="badge" className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };
