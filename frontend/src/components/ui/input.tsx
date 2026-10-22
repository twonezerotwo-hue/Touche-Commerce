import * as React from "react";

import { cn } from "@/lib/utils";

function Input({ className, type = "text", ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "h-10 w-full rounded-md border border-white/10 bg-ink-950/70 px-3 text-[13px] text-mist-100",
        "shadow-[inset_0_1px_0_0_rgb(255_255_255/0.03)] placeholder:text-mist-600",
        "transition-[border-color,box-shadow] duration-200 focus:border-accent-400/55 focus:ring-2 focus:ring-accent-400/15 focus:outline-none",
        "disabled:cursor-not-allowed disabled:opacity-60",
        "aria-[invalid=true]:border-crimson-400/60 aria-[invalid=true]:ring-crimson-400/15",
        className,
      )}
      {...props}
    />
  );
}

export { Input };
