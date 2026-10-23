import * as React from "react";

import { cn } from "@/lib/utils";

export interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
  /**
   * Drop the panel chrome. Use it when the empty state already sits inside a panel
   * (a table wrapper), so the screen shows one surface instead of a box in a box.
   */
  embedded?: boolean;
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
  embedded = false,
}: EmptyStateProps) {
  return (
    <div
      data-embedded={embedded ? "true" : undefined}
      className={cn(
        "flex flex-col items-center px-6 py-12 text-center",
        embedded ? "py-10" : "panel rounded-xl",
        className,
      )}
    >
      {icon ? (
        <span className="mb-4 flex size-11 items-center justify-center rounded-full border border-white/10 bg-white/[0.03] text-mist-400">
          {icon}
        </span>
      ) : null}
      <p className="font-display text-[17px] text-mist-200">{title}</p>
      {description ? (
        <p className="mx-auto mt-2 max-w-sm text-[12px] leading-relaxed text-mist-500">
          {description}
        </p>
      ) : null}
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}
