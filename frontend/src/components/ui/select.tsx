import * as React from "react";
import { ChevronDown } from "lucide-react";

import { cn } from "@/lib/utils";

function Select({ className, children, ...props }: React.ComponentProps<"select">) {
  return (
    <div className="relative">
      <select
        data-slot="select"
        className={cn(
          "h-10 w-full appearance-none rounded-md border border-white/10 bg-ink-950/70 px-3 pr-9 text-[13px] text-mist-100",
          "shadow-[inset_0_1px_0_0_rgb(255_255_255/0.03)]",
          "transition-[border-color,box-shadow] duration-200 focus:border-accent-400/55 focus:ring-2 focus:ring-accent-400/15 focus:outline-none",
          "disabled:cursor-not-allowed disabled:opacity-60",
          "aria-[invalid=true]:border-crimson-400/60",
          className,
        )}
        {...props}
      >
        {children}
      </select>
      <ChevronDown
        className="pointer-events-none absolute top-1/2 right-3 size-3.5 -translate-y-1/2 text-mist-500"
        aria-hidden
      />
    </div>
  );
}

export { Select };
