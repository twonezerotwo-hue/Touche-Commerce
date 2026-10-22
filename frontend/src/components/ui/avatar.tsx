import { cn } from "@/lib/utils";

const TONES = [
  "border-accent-400/30 bg-accent-400/10 text-accent-200",
  "border-cyan-400/25 bg-cyan-400/[0.08] text-cyan-300",
  "border-jade-400/25 bg-jade-400/[0.08] text-jade-400",
  "border-amber-400/25 bg-amber-400/[0.08] text-amber-400",
] as const;

export function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/).slice(0, 2);
  return parts.map((part) => part[0]?.toUpperCase() ?? "").join("") || "•";
}

function toneFor(name: string): (typeof TONES)[number] {
  let hash = 0;
  for (let index = 0; index < name.length; index += 1) {
    hash = (hash * 31 + name.charCodeAt(index)) % 997;
  }
  return TONES[hash % TONES.length];
}

/** Initials avatar with a deterministic tone, so the same entity keeps its colour. */
export function Avatar({
  name,
  className,
  size = "md",
}: {
  name: string;
  className?: string;
  size?: "sm" | "md";
}) {
  return (
    <span
      aria-hidden
      className={cn(
        "flex shrink-0 items-center justify-center rounded-full border font-medium tracking-[0.04em]",
        size === "sm" ? "size-7 text-[10px]" : "size-9 text-[11px]",
        toneFor(name),
        className,
      )}
    >
      {initialsOf(name)}
    </span>
  );
}
