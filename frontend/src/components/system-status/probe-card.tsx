import { Badge } from "@/components/ui/badge";
import { Card, CardTitle } from "@/components/ui/card";
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
      <div className="px-5 pt-4.5">
        <div className="flex items-center justify-between gap-3">
          <span className="eyebrow">{eyebrow}</span>
          <Badge variant={PROBE_STATE_BADGE[state]}>
            <span className={cn("size-1.5 rounded-full", PROBE_STATE_DOT[state])} aria-hidden />
            {PROBE_STATE_LABEL[state]}
          </Badge>
        </div>
        <CardTitle className="mt-2.5">{title}</CardTitle>
        <p className="mt-1.5 text-[11.5px] leading-relaxed break-words text-mist-400">{value}</p>
      </div>

      {rows.length > 0 ? (
        <div className="mt-4 px-5">
          <dl className="panel-inset">
            {rows.map((row, index) => (
              <div
                key={row.label}
                className={cn(
                  "flex items-baseline justify-between gap-4 px-3 py-2",
                  index > 0 && "border-t border-white/[0.05]",
                )}
              >
                <dt className="shrink-0 text-[10px] tracking-[0.14em] text-mist-600 uppercase">
                  {row.label}
                </dt>
                <dd
                  className={cn(
                    "min-w-0 text-right text-[11.5px] break-words text-mist-200",
                    row.mono && "font-mono text-[11px]",
                    row.muted && "text-mist-500",
                  )}
                >
                  {row.value}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      ) : null}

      {footer ? (
        <div className="mt-auto px-5 pt-4 pb-4">
          <p className="text-[10.5px] leading-relaxed text-mist-600">{footer}</p>
        </div>
      ) : (
        <div className="pb-1" />
      )}
    </Card>
  );
}
