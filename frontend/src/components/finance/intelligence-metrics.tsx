import { ClassificationBadge } from "@/components/finance/reconciliation-status-badge";
import { Badge } from "@/components/ui/badge";
import { completenessTone, metricLines, type IntelligenceMetric } from "@/lib/finance/intelligence";

/**
 * One analysis metric. Money and percentages are listed per currency and are
 * never summed; an unavailable metric says so in words instead of showing 0.
 */
export function MetricCard({ metric }: { metric: IntelligenceMetric }) {
  const lines = metricLines(metric);
  const kind =
    lines.length === 0
      ? "UNAVAILABLE"
      : metric.classification === "VERIFIED"
        ? null
        : metric.classification;
  return (
    <div className="panel p-4" data-metric={metric.key}>
      <div className="flex items-start justify-between gap-3">
        <p className="eyebrow">{metric.label}</p>
        {/* The API names a metric's kind. With no figure to show it must not wear that label,
            and VERIFIED is a reviewer's decision on one run: a coverage ratio cannot carry it
            (a 0.00% coverage under a green VERIFIED badge reads as a claim). */}
        {kind ? <ClassificationBadge value={kind} /> : null}
      </div>
      {lines.length === 0 ? (
        <p className="mt-3 font-display text-[20px] leading-none text-mist-500">Not available</p>
      ) : (
        <ul className="mt-3 space-y-1.5">
          {lines.map((line) => (
            <li
              key={`${line.currency ?? "count"}-${line.text}`}
              className="flex items-baseline justify-between gap-3"
            >
              <span className="data-value font-display text-[22px] leading-none text-mist-100">
                {line.text}
              </span>
              {line.currency ? (
                <span className="font-mono text-[10px] text-mist-600">{line.currency}</span>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      <p className="mt-3 text-[11px] leading-relaxed text-mist-500">{metric.meaning}</p>
      <div className="mt-2">
        <Badge variant={completenessTone(metric.completeness)}>{metric.completeness}</Badge>
      </div>
    </div>
  );
}

export function MetricGrid({ metrics }: { metrics: readonly IntelligenceMetric[] }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {metrics.map((metric) => (
        <MetricCard key={metric.key} metric={metric} />
      ))}
    </div>
  );
}
