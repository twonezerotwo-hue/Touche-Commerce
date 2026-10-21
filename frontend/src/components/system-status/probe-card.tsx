import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  PROBE_STATE_BADGE,
  PROBE_STATE_DOT,
  PROBE_STATE_LABEL,
  type ProbeState,
} from "@/lib/status";
import { cn } from "@/lib/utils";

export interface ProbeRow {
  label: string;
  value: string;
  mono?: boolean;
  muted?: boolean;
}

export interface ProbeCardProps {
  eyebrow: string;
  title: string;
  state: ProbeState;
  value: string;
  rows: readonly ProbeRow[];
  footer?: string;
}

export function ProbeCard({ eyebrow, title, state, value, rows, footer }: ProbeCardProps) {
  return (
    <Card className="flex h-full flex-col" data-probe-state={state}>
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <span className="eyebrow">{eyebrow}</span>
          <Badge variant={PROBE_STATE_BADGE[state]}>
            <span className={cn("size-1.5 rounded-full", PROBE_STATE_DOT[state])} aria-hidden />
            {PROBE_STATE_LABEL[state]}
          </Badge>
        </div>
        <CardTitle>{title}</CardTitle>
        <p className="text-[13px] leading-relaxed text-mist-300">{value}</p>
      </CardHeader>
      <CardContent className="mt-auto space-y-2.5 pt-1">
        {rows.map((row) => (
          <div key={row.label} className="flex items-baseline justify-between gap-4">
            <span className="shrink-0 text-[10.5px] uppercase tracking-[0.14em] text-mist-600">
              {row.label}
            </span>
            <span
              className={cn(
                "min-w-0 break-words text-right text-[12px] text-mist-200",
                row.mono && "font-mono text-[11.5px]",
                row.muted && "text-mist-500",
              )}
            >
              {row.value}
            </span>
          </div>
        ))}
        {footer ? (
          <>
            <div className="rule mt-3" />
            <p className="pt-1 text-[11px] leading-relaxed text-mist-600">{footer}</p>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
