import * as React from "react";

import { cn } from "@/lib/utils";

export interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}

export function EmptyState({ icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        "panel flex flex-col items-center rounded-xl px-6 py-12 text-center",
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
