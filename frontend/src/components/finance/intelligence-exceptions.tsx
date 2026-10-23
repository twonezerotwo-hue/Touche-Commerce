import Link from "next/link";

import { DiscrepancyResolutionForm } from "@/components/finance/reconciliation-actions";
import { DiscrepancySeverityBadge } from "@/components/finance/reconciliation-status-badge";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { humanize, type FinancialException } from "@/lib/finance/intelligence";
import { formatDate } from "@/lib/trade/format";

/** Stage 5D discrepancies enriched with the affected order; resolution is unchanged. */
export function IntelligenceExceptionsTable({
  items,
  csrfToken,
  canReview,
}: {
  items: readonly FinancialException[];
  csrfToken: string;
  canReview: boolean;
}) {
  if (items.length === 0) {
    return (
      <EmptyState
        title="No financial exceptions"
        description="No exceptions match the current filters."
      />
    );
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="pl-4">Order</TableHead>
          <TableHead>Exception</TableHead>
          <TableHead className="pr-4">Finding and resolution</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {/* Three columns on purpose: the finding gets the width it needs and the
            resolution control sits under it, so it is never scrolled out of view. */}
        {items.map((item) => (
          <TableRow key={item.id}>
            <TableCell className="min-w-[160px] pl-4 align-top">
              <Link
                href={`/finance/intelligence/orders/${item.sales_order_id}`}
                className="font-mono text-[11.5px] whitespace-nowrap text-accent-200 hover:text-accent-100"
              >
                {item.order_number}
              </Link>
              <span
                className="mt-0.5 line-clamp-2 max-w-[200px] text-[10px] text-mist-600"
                title={item.customer_name}
              >
                {item.customer_name}
              </span>
              <span className="mt-0.5 block font-mono text-[10px] text-mist-600">
                {item.currency} · {formatDate(item.created_at)}
              </span>
            </TableCell>
            <TableCell className="min-w-[190px] align-top">
              <span className="flex flex-col items-start gap-1">
                <Badge variant="secondary">{humanize(item.code)}</Badge>
                <span className="flex flex-wrap items-center gap-1">
                  <DiscrepancySeverityBadge severity={item.severity} />
                  <Badge variant={item.status === "RESOLVED" ? "success" : "outline"}>
                    {item.status}
                  </Badge>
                </span>
              </span>
            </TableCell>
            <TableCell className="min-w-[280px] pr-4 align-top">
              <p className="text-[11px] text-mist-200">{item.title}</p>
              <p className="mt-0.5 text-[10px] leading-relaxed text-mist-600">{item.detail}</p>
              <p className="mt-1.5 text-[10px] text-mist-500">
                {item.finance_source_reference ? (
                  <>
                    Finance source{" "}
                    <span className="font-mono text-mist-300">{item.finance_source_reference}</span>
                  </>
                ) : (
                  "No Finance reference"
                )}
                {" · "}
                <Link
                  href={`/finance/reconciliation/${item.run_id}`}
                  className="font-mono text-accent-200 hover:text-accent-100"
                >
                  Open run
                </Link>
              </p>
              {item.resolution_notes ? (
                <div className="mt-2">
                  <p className="text-[10px] text-jade-400">{item.resolution_notes}</p>
                  {item.reviewer_name ? (
                    <p className="mt-0.5 text-[10px] text-mist-600">{item.reviewer_name}</p>
                  ) : null}
                </div>
              ) : (
                <DiscrepancyResolutionForm
                  discrepancy={item}
                  csrfToken={csrfToken}
                  canReview={canReview}
                />
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
