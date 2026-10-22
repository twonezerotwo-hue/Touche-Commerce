import * as React from "react";

import { cn } from "@/lib/utils";

export interface StatProps {
  label: string;
  value: React.ReactNode;
  detail?: React.ReactNode;
  icon?: React.ReactNode;
  /** 0–100 share, rendered as a hairline meter. Only pass real proportions. */
  share?: number;
  tone?: "accent" | "jade" | "amber" | "neutral";
  className?: string;
}

const TONE_BAR: Record<NonNullable<StatProps["tone"]>, string> = {
  accent: "bg-accent-400",
  jade: "bg-jade-400",
  amber: "bg-amber-400",
  neutral: "bg-mist-500",
};

/** Compact KPI tile. No invented deltas: the detail line states the source. */
export function Stat({ label, value, detail, icon, share, tone = "accent", className }: StatProps) {
  return (
    <div
      className={cn(
        "panel group relative overflow-hidden p-4 transition-colors duration-200 hover:border-white/12",
        className,
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <p className="eyebrow">{label}</p>
        {icon ? <span className="text-mist-500">{icon}</span> : null}
      </div>
      <p className="data-value mt-3 font-display text-[26px] leading-none text-mist-100">{value}</p>
      {detail ? <p className="mt-2 text-[11px] leading-relaxed text-mist-500">{detail}</p> : null}
      {typeof share === "number" ? (
        <div className="mt-3 h-px w-full bg-white/[0.07]" aria-hidden>
          <div
            className={cn("h-px transition-[width] duration-500", TONE_BAR[tone])}
            style={{ width: `${Math.max(0, Math.min(100, share))}%` }}
          />
        </div>
      ) : null}
    </div>
  );
}
