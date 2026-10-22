import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md font-medium transition-all duration-200 focus-visible:outline-none disabled:pointer-events-none disabled:opacity-45 active:translate-y-px",
  {
    variants: {
      variant: {
        default:
          "border border-accent-400/40 bg-gradient-to-b from-accent-400 to-accent-500 text-ink-950 shadow-[0_8px_20px_-12px_rgb(47_127_232/0.9)] hover:from-accent-300 hover:to-accent-400",
        outline:
          "border border-white/10 bg-white/[0.025] text-mist-200 hover:border-accent-400/40 hover:bg-white/[0.055] hover:text-mist-100",
        subtle:
          "border border-transparent bg-white/[0.05] text-mist-200 hover:bg-white/[0.08] hover:text-mist-100",
        ghost: "border border-transparent text-mist-300 hover:bg-white/[0.05] hover:text-mist-100",
        danger:
          "border border-crimson-400/35 bg-crimson-400/10 text-crimson-400 hover:border-crimson-400/55 hover:bg-crimson-400/15",
        link: "text-accent-300 underline-offset-4 hover:text-accent-200 hover:underline",
      },
      size: {
        default: "h-9 px-4 text-[12.5px]",
        sm: "h-8 rounded-md px-3 text-[11.5px]",
        xs: "h-7 rounded px-2.5 text-[11px]",
        icon: "size-9",
        iconSm: "size-8 rounded-md",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

function Button({ className, variant, size, asChild = false, ...props }: ButtonProps) {
  const Comp = asChild ? Slot : "button";
  return (
    <Comp
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  );
}

export { Button, buttonVariants };
