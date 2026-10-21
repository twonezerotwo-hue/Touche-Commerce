import * as React from "react";

import { cn } from "@/lib/utils";

function Separator({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="separator"
      role="separator"
      aria-orientation="horizontal"
      className={cn("h-px w-full bg-white/[0.06]", className)}
      {...props}
    />
  );
}

export { Separator };
