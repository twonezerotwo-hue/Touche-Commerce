import * as React from "react";

import { cn } from "@/lib/utils";

function Label({ className, ...props }: React.ComponentProps<"label">) {
  return (
    <label
      data-slot="label"
      className={cn(
        "block text-[10px] font-medium uppercase tracking-[0.15em] text-mist-500",
        className,
      )}
      {...props}
    />
  );
}

export { Label };
