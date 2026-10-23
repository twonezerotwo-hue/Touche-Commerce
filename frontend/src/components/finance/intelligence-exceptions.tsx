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
          <TableHead>Severity</TableHead>
          <TableHead>Finding</TableHead>
          <TableHead>Source</TableHead>
          <TableHead>Created</TableHead>
          <TableHead className="pr-4">Resolution</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {items.map((item) => (
          <TableRow key={item.id}>
            <TableCell className="pl-4">
              <Link
                href={`/finance/intelligence/orders/${item.sales_order_id}`}
                className="font-mono text-[11.5px] text-accent-200 hover:text-accent-100"
              >
                {item.order_number}
              </Link>
              <span className="block text-[10px] text-mist-600">{item.customer_name}</span>
              <span className="block font-mono text-[10px] text-mist-600">{item.currency}</span>
            </TableCell>
            <TableCell>
              <Badge variant="secondary">{humanize(item.code)}</Badge>
              <Badge className="mt-1" variant={item.status === "RESOLVED" ? "success" : "outline"}>
                {item.status}
              </Badge>
            </TableCell>
            <TableCell>
              <DiscrepancySeverityBadge severity={item.severity} />
            </TableCell>
            <TableCell className="max-w-[360px]">
              <p className="text-[11px] text-mist-200">{item.title}</p>
              <p className="mt-0.5 text-[10px] leading-relaxed text-mist-600">{item.detail}</p>
            </TableCell>
            <TableCell className="text-[10px] text-mist-500">
              {item.finance_source_reference ? (
                <span className="font-mono text-mist-300">{item.finance_source_reference}</span>
              ) : (
                <span>No Finance reference</span>
              )}
              <Link
                href={`/finance/reconciliation/${item.run_id}`}
                className="mt-1 block font-mono text-accent-200 hover:text-accent-100"
              >
                Open run
              </Link>
            </TableCell>
            <TableCell className="text-[10px] whitespace-nowrap text-mist-600">
              {formatDate(item.created_at)}
            </TableCell>
            <TableCell className="pr-4">
              {item.resolution_notes ? (
                <>
                  <p className="max-w-[220px] text-[10px] text-jade-400">{item.resolution_notes}</p>
                  {item.reviewer_name ? (
                    <p className="mt-0.5 text-[10px] text-mist-600">{item.reviewer_name}</p>
                  ) : null}
                </>
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
