import * as React from "react";
import { ChevronDown } from "lucide-react";

import { cn } from "@/lib/utils";

function Select({ className, children, ...props }: React.ComponentProps<"select">) {
  return (
    <div className="relative">
      <select
        data-slot="select"
        className={cn(
          "h-10 w-full appearance-none rounded-md border border-white/10 bg-ink-950/60 px-3 pr-9 text-[13px] text-mist-100",
          "transition-colors focus:border-gold-400/50 focus:outline-none",
          "disabled:cursor-not-allowed disabled:opacity-60",
          "aria-[invalid=true]:border-crimson-400/60",
          className,
        )}
        {...props}
      >
        {children}
      </select>
      <ChevronDown
        className="pointer-events-none absolute right-3 top-1/2 size-3.5 -translate-y-1/2 text-mist-500"
        aria-hidden
      />
    </div>
  );
}

export { Select };
