import { cn } from "@/lib/utils";

const TONES = {
  accent: "bg-gradient-to-r from-accent-500 to-accent-300",
  cyan: "bg-gradient-to-r from-accent-500 to-cyan-400",
  jade: "bg-gradient-to-r from-jade-500 to-jade-400",
  amber: "bg-gradient-to-r from-amber-400/70 to-amber-400",
  crimson: "bg-gradient-to-r from-crimson-500 to-crimson-400",
  neutral: "bg-mist-500",
} as const;

export interface MeterProps {
  /** Percentage 0–100. */
  value: number;
  tone?: keyof typeof TONES;
  className?: string;
  /** Accessible label; omit when the meter is purely decorative next to text. */
  label?: string;
}

/** Thin proportional bar used for pipeline and status distributions. */
export function Meter({ value, tone = "accent", className, label }: MeterProps) {
  const width = Math.max(0, Math.min(100, Number.isFinite(value) ? value : 0));
  return (
    <div
      className={cn("h-1 w-full overflow-hidden rounded-full bg-white/[0.06]", className)}
      role={label ? "progressbar" : undefined}
      aria-label={label}
      aria-valuenow={label ? Math.round(width) : undefined}
      aria-valuemin={label ? 0 : undefined}
      aria-valuemax={label ? 100 : undefined}
    >
      <div
        className={cn("h-full rounded-full transition-[width] duration-700", TONES[tone])}
        style={{ width: `${width}%` }}
      />
    </div>
  );
}
