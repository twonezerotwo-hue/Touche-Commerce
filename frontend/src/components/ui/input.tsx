import * as React from "react";

import { cn } from "@/lib/utils";

function Input({ className, type = "text", ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "h-10 w-full rounded-md border border-white/10 bg-ink-950/60 px-3 text-[13px] text-mist-100",
        "placeholder:text-mist-600 transition-colors focus:border-gold-400/50 focus:outline-none",
        "disabled:cursor-not-allowed disabled:opacity-60",
        "aria-[invalid=true]:border-crimson-400/60",
        className,
      )}
      {...props}
    />
  );
}

export { Input };
