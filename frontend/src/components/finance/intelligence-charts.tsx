import * as React from "react";

import { EmptyState } from "@/components/ui/empty-state";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  barShare,
  COMPLETENESS_LABELS,
  groupByCurrency,
  humanize,
  maxAbs,
  tooltipAlign,
  type CategoryCount,
  type Completeness,
  type CompletenessCount,
  type CostComparison,
  type MarginBucket,
  type MonthlyCommitment,
  type TooltipAlign,
} from "@/lib/finance/intelligence";
import { formatMoney } from "@/lib/trade/format";
import { cn } from "@/lib/utils";

/**
 * Two-series categorical pair, validated with the dataviz validator against the
 * panel surface (#0f1723, dark): lightness band, chroma, CVD ΔE 26.8 and
 * normal-vision ΔE 31.8 all pass. The app theme's accent/cyan pair fails the
 * normal-vision floor, so it is deliberately not used for two series.
 */
const SERIES = {
  one: { bar: "bg-[#3987e5]", label: "bg-[#3987e5]" },
  two: { bar: "bg-[#d95926]", label: "bg-[#d95926]" },
} as const;

/** Status colours are reserved for completeness states and always carry a label. */
const STATUS_BAR: Record<Completeness, string> = {
  COMPLETE: "bg-jade-400",
  PARTIAL: "bg-amber-400",
  MISSING: "bg-crimson-400",
  UNAVAILABLE: "bg-mist-500",
};

/**
 * Hover/focus tooltip. `align` keeps it inside its chart for marks near either
 * edge; `inside` places it over the plot instead of above it, for plots that
 * scroll horizontally (a scroll container would clip a tooltip above it).
 */
function Tip({
  children,
  align = "center",
  inside = false,
}: {
  children: React.ReactNode;
  align?: TooltipAlign;
  inside?: boolean;
}) {
  return (
    <span
      aria-hidden
      className={cn(
        "pointer-events-none absolute z-10 hidden rounded-md border border-white/10 bg-ink-900 px-2 py-1 text-left text-[10.5px] leading-snug whitespace-nowrap text-mist-200 shadow-lg group-hover:block group-focus-visible:block",
        inside ? "top-0" : "bottom-full mb-1.5",
        align === "start" ? "left-0" : align === "end" ? "right-0" : "left-1/2 -translate-x-1/2",
      )}
    >
      {children}
    </span>
  );
}

function Legend({ items }: { items: Array<{ label: string; swatch: string }> }) {
  return (
    <ul className="flex flex-wrap items-center gap-x-4 gap-y-1" aria-label="Legend">
      {items.map((item) => (
        <li key={item.label} className="flex items-center gap-1.5 text-[10.5px] text-mist-400">
          <span className={cn("size-2 rounded-[2px]", item.swatch)} aria-hidden />
          {item.label}
        </li>
      ))}
    </ul>
  );
}

function ChartPanel({
  title,
  description,
  legend,
  table,
  children,
  className,
}: {
  title: string;
  description?: string;
  legend?: Array<{ label: string; swatch: string }>;
  table?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    // min-w-0: a grid item otherwise grows to its widest content, so a scrolling plot or
    // table inside would still widen the whole page instead of scrolling in its panel.
    <section className={cn("panel flex min-w-0 flex-col gap-3 p-4", className)} aria-label={title}>
      <div>
        <h3 className="eyebrow">{title}</h3>
        {description ? (
          <p className="mt-1 text-[10.5px] leading-relaxed text-mist-600">{description}</p>
        ) : null}
      </div>
      {legend && legend.length > 1 ? <Legend items={legend} /> : null}
      <div className="min-w-0 flex-1">{children}</div>
      {table ? (
        <details className="text-[10.5px] text-mist-500">
          <summary className="cursor-pointer select-none hover:text-mist-200">Table view</summary>
          <div className="mt-2 overflow-x-auto">{table}</div>
        </details>
      ) : null}
    </section>
  );
}

function ChartEmpty({ title }: { title: string }) {
  return (
    <EmptyState
      className="border-0 bg-transparent py-6 shadow-none"
      title={title}
      description="No orders in the selected range have data for this view."
    />
  );
}

function CurrencyLabel({ currency }: { currency: string }) {
  return <p className="mb-2 font-mono text-[10.5px] text-mist-400">{currency}</p>;
}

/** Accepted value vs purchase commitments per month, one panel per currency. */
export function MonthlyCommitmentsChart({ rows }: { rows: readonly MonthlyCommitment[] }) {
  const legend = [
    { label: "Accepted value", swatch: SERIES.one.label },
    { label: "Purchase commitments", swatch: SERIES.two.label },
  ];
  const groups = groupByCurrency(rows);
  return (
    <ChartPanel
      title="Monthly commitments"
      description="Accepted order value beside committed purchase orders. Each currency has its own scale; currencies are never added together."
      legend={legend}
      table={
        rows.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Month</TableHead>
                <TableHead>Currency</TableHead>
                <TableHead className="text-right">Accepted value</TableHead>
                <TableHead className="text-right">Purchase commitments</TableHead>
                <TableHead className="text-right">Orders</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={`${row.currency}-${row.month}`}>
                  <TableCell className="font-mono">{row.month}</TableCell>
                  <TableCell className="font-mono">{row.currency}</TableCell>
                  <TableCell className="text-right font-mono">
                    {formatMoney(row.accepted_value, row.currency)}
                  </TableCell>
                  <TableCell className="text-right font-mono">
                    {formatMoney(row.purchase_commitments, row.currency)}
                  </TableCell>
                  <TableCell className="text-right font-mono">{row.order_count}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : undefined
      }
    >
      {groups.length === 0 ? (
        <ChartEmpty title="No monthly commitments" />
      ) : (
        <div className="space-y-5">
          {groups.map(({ currency, rows: monthRows }) => {
            const maximum = maxAbs(
              monthRows.flatMap((r) => [r.accepted_value, r.purchase_commitments]),
            );
            return (
              <div key={currency}>
                <CurrencyLabel currency={currency} />
                {/* A year of months is the normal case: the plot scrolls inside its panel
                    instead of widening the page. */}
                <div className="overflow-x-auto" data-chart-scroll>
                  <div className="flex h-36 items-stretch gap-2" role="list">
                    {monthRows.map((row, index) => {
                      const accepted = barShare(row.accepted_value, maximum);
                      const committed = barShare(row.purchase_commitments, maximum);
                      const orders = `${row.order_count} order${row.order_count === 1 ? "" : "s"}`;
                      const summary = `${row.month} · ${currency} · accepted ${formatMoney(row.accepted_value, currency)} · commitments ${formatMoney(row.purchase_commitments, currency)} · ${orders}`;
                      return (
                        <div
                          key={row.month}
                          role="listitem"
                          tabIndex={0}
                          aria-label={summary}
                          className="group relative flex h-full min-w-11 flex-1 flex-col rounded outline-none focus-visible:ring-1 focus-visible:ring-accent-400"
                        >
                          <Tip align={tooltipAlign(index, monthRows.length)} inside>
                            <span className="block font-mono text-mist-100">{row.month}</span>
                            <span className="block">
                              Accepted {formatMoney(row.accepted_value, currency)}
                            </span>
                            <span className="block">
                              Commitments {formatMoney(row.purchase_commitments, currency)}
                            </span>
                            <span className="block text-mist-500">{orders}</span>
                          </Tip>
                          <div className="flex min-h-0 flex-1 items-end justify-center gap-0.5">
                            <div
                              className={cn("w-3 rounded-t-[4px]", SERIES.one.bar)}
                              style={{ height: `${accepted > 0 ? Math.max(accepted, 2) : 0}%` }}
                            />
                            <div
                              className={cn("w-3 rounded-t-[4px]", SERIES.two.bar)}
                              style={{ height: `${committed > 0 ? Math.max(committed, 2) : 0}%` }}
                            />
                          </div>
                          <p className="mt-1.5 shrink-0 text-center font-mono text-[9.5px] whitespace-nowrap text-mist-500">
                            {row.month}
                          </p>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </ChartPanel>
  );
}

/** Estimated vs documented cost per currency; bars compare within a currency only. */
export function CostComparisonChart({ rows }: { rows: readonly CostComparison[] }) {
  const legend = [
    { label: "Estimated cost", swatch: SERIES.one.label },
    { label: "Documented cost", swatch: SERIES.two.label },
  ];
  return (
    <ChartPanel
      title="Estimated vs documented cost"
      description="Only orders with a complete estimate and a complete documented basis. Variance is documented minus estimated."
      legend={legend}
      table={
        rows.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Currency</TableHead>
                <TableHead className="text-right">Estimated</TableHead>
                <TableHead className="text-right">Documented</TableHead>
                <TableHead className="text-right">Variance</TableHead>
                <TableHead className="text-right">Orders</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.currency}>
                  <TableCell className="font-mono">{row.currency}</TableCell>
                  <TableCell className="text-right font-mono">
                    {formatMoney(row.estimated_cost, row.currency)}
                  </TableCell>
                  <TableCell className="text-right font-mono">
                    {formatMoney(row.documented_cost, row.currency)}
                  </TableCell>
                  <TableCell className="text-right font-mono">
                    {formatMoney(row.variance, row.currency)}
                  </TableCell>
                  <TableCell className="text-right font-mono">{row.order_count}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : undefined
      }
    >
      {rows.length === 0 ? (
        <ChartEmpty title="No comparable orders" />
      ) : (
        <div className="space-y-5">
          {rows.map((row) => {
            const maximum = maxAbs([row.estimated_cost, row.documented_cost]);
            const estimated = barShare(row.estimated_cost, maximum);
            const documented = barShare(row.documented_cost, maximum);
            return (
              <div key={row.currency}>
                <div className="mb-2 flex items-baseline justify-between gap-3">
                  <p className="font-mono text-[10.5px] text-mist-400">{row.currency}</p>
                  <p className="text-[10.5px] text-mist-400">
                    Variance{" "}
                    <span className="font-mono text-mist-200">
                      {formatMoney(row.variance, row.currency)}
                    </span>{" "}
                    · {row.order_count} order{row.order_count === 1 ? "" : "s"}
                  </p>
                </div>
                <dl className="space-y-1.5">
                  {(
                    [
                      ["Estimated", row.estimated_cost, estimated, SERIES.one.bar],
                      ["Documented", row.documented_cost, documented, SERIES.two.bar],
                    ] as const
                  ).map(([label, value, share, color]) => (
                    <div
                      key={label}
                      className="group relative grid grid-cols-[84px_1fr_auto] items-center gap-3 rounded outline-none focus-visible:ring-1 focus-visible:ring-accent-400"
                      tabIndex={0}
                      aria-label={`${label} cost ${formatMoney(value, row.currency)}`}
                    >
                      <dt className="text-[10.5px] text-mist-500">{label}</dt>
                      <dd className="h-2 rounded-[3px] bg-white/[0.05]">
                        <div
                          className={cn("h-2 rounded-r-[4px]", color)}
                          style={{ width: `${share > 0 ? Math.max(share, 2) : 0}%` }}
                        />
                      </dd>
                      <dd className="font-mono text-[10.5px] text-mist-200">
                        {formatMoney(value, row.currency)}
                      </dd>
                    </div>
                  ))}
                </dl>
              </div>
            );
          })}
        </div>
      )}
    </ChartPanel>
  );
}

/** Order count per margin bucket (single series). */
export function MarginDistributionChart({ buckets }: { buckets: readonly MarginBucket[] }) {
  const total = buckets.reduce((sum, bucket) => sum + bucket.count, 0);
  const maximum = Math.max(0, ...buckets.map((bucket) => bucket.count));
  return (
    <ChartPanel
      title="Estimated margin distribution"
      description="Orders per estimated gross-margin band. Orders without a complete estimate are not placed in a band."
      table={
        buckets.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Band</TableHead>
                <TableHead className="text-right">Orders</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {buckets.map((bucket) => (
                <TableRow key={bucket.key}>
                  <TableCell>{bucket.label}</TableCell>
                  <TableCell className="text-right font-mono">{bucket.count}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : undefined
      }
    >
      {total === 0 ? (
        <ChartEmpty title="No margin data" />
      ) : (
        <div className="flex h-32 items-end gap-3" role="list">
          {buckets.map((bucket) => (
            <div
              key={bucket.key}
              role="listitem"
              tabIndex={0}
              aria-label={`${bucket.label}: ${bucket.count} order${bucket.count === 1 ? "" : "s"}`}
              className="group relative flex h-full min-w-8 flex-1 flex-col justify-end rounded outline-none focus-visible:ring-1 focus-visible:ring-accent-400"
            >
              <Tip>
                <span className="block text-mist-100">{bucket.label}</span>
                <span className="block">
                  {bucket.count} order{bucket.count === 1 ? "" : "s"}
                </span>
              </Tip>
              <p className="mb-1 text-center font-mono text-[10px] text-mist-300">{bucket.count}</p>
              <div className="flex flex-1 items-end justify-center">
                <div
                  className={cn("w-5 rounded-t-[4px]", SERIES.one.bar)}
                  style={{
                    height: `${bucket.count > 0 ? Math.max((bucket.count / maximum) * 100, 3) : 0}%`,
                  }}
                />
              </div>
              <p className="mt-1.5 text-center text-[9.5px] leading-tight text-mist-500">
                {bucket.label}
              </p>
            </div>
          ))}
        </div>
      )}
    </ChartPanel>
  );
}

/** Ranked counts per category (single series, ordered by count). */
export function RankedCountChart({
  title,
  description,
  items,
  emptyTitle,
  columnLabel = "Count",
}: {
  title: string;
  description?: string;
  items: readonly CategoryCount[];
  emptyTitle: string;
  columnLabel?: string;
}) {
  const ranked = [...items].sort((a, b) => b.count - a.count || a.key.localeCompare(b.key));
  const maximum = Math.max(0, ...ranked.map((item) => item.count));
  return (
    <ChartPanel
      title={title}
      description={description}
      table={
        ranked.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Category</TableHead>
                <TableHead className="text-right">{columnLabel}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {ranked.map((item) => (
                <TableRow key={item.key}>
                  <TableCell>{humanize(item.key)}</TableCell>
                  <TableCell className="text-right font-mono">{item.count}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : undefined
      }
    >
      {ranked.length === 0 ? (
        <ChartEmpty title={emptyTitle} />
      ) : (
        <ul className="space-y-2">
          {ranked.map((item) => (
            <li
              key={item.key}
              tabIndex={0}
              aria-label={`${humanize(item.key)}: ${item.count}`}
              className="group relative grid grid-cols-[minmax(0,1fr)_2fr_auto] items-center gap-3 rounded outline-none focus-visible:ring-1 focus-visible:ring-accent-400"
            >
              <span className="truncate text-[10.5px] text-mist-400">{humanize(item.key)}</span>
              <span className="h-2 rounded-[3px] bg-white/[0.05]">
                <span
                  className={cn("block h-2 rounded-r-[4px]", SERIES.one.bar)}
                  style={{
                    width: `${item.count > 0 && maximum > 0 ? Math.max((item.count / maximum) * 100, 3) : 0}%`,
                  }}
                />
              </span>
              <span className="font-mono text-[10.5px] text-mist-200">{item.count}</span>
            </li>
          ))}
        </ul>
      )}
    </ChartPanel>
  );
}

/** Part-to-whole completeness; every segment is named with its count. */
export function CompletenessBar({
  title,
  description,
  counts,
}: {
  title: string;
  description?: string;
  counts: readonly CompletenessCount[];
}) {
  const total = counts.reduce((sum, item) => sum + item.count, 0);
  return (
    <ChartPanel
      title={title}
      description={description}
      table={
        counts.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Orders</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {counts.map((item) => (
                <TableRow key={item.status}>
                  <TableCell>{COMPLETENESS_LABELS[item.status]}</TableCell>
                  <TableCell className="text-right font-mono">{item.count}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : undefined
      }
    >
      {total === 0 ? (
        <ChartEmpty title="No orders" />
      ) : (
        <div className="space-y-3">
          <div className="flex h-2.5 w-full gap-0.5 overflow-hidden rounded-[4px]" aria-hidden>
            {counts
              .filter((item) => item.count > 0)
              .map((item) => (
                <div
                  key={item.status}
                  className={cn("h-full", STATUS_BAR[item.status])}
                  style={{ width: `${(item.count / total) * 100}%` }}
                />
              ))}
          </div>
          <ul className="grid grid-cols-2 gap-x-4 gap-y-1.5 sm:grid-cols-4">
            {counts.map((item) => (
              <li key={item.status} className="flex items-center gap-1.5 text-[10.5px]">
                <span className={cn("size-2 rounded-[2px]", STATUS_BAR[item.status])} aria-hidden />
                <span className="text-mist-400">{COMPLETENESS_LABELS[item.status]}</span>
                <span className="ml-auto font-mono text-mist-200">{item.count}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </ChartPanel>
  );
}
