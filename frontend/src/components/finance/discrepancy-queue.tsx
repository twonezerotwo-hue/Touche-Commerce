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
import type { ReconciliationDiscrepancy } from "@/lib/finance/reconciliation";
import { formatDate } from "@/lib/trade/format";

export function DiscrepancyQueue({
  items,
  csrfToken,
  canReview,
}: {
  items: ReconciliationDiscrepancy[];
  csrfToken: string;
  canReview: boolean;
}) {
  if (items.length === 0) {
    return (
      <EmptyState
        title="No discrepancies"
        description="No deterministic exceptions match the current filters."
      />
    );
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="pl-4">Code</TableHead>
          <TableHead>Severity</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Finding</TableHead>
          <TableHead>Run</TableHead>
          <TableHead>Created</TableHead>
          <TableHead className="pr-4">Resolution</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {items.map((item) => (
          <TableRow key={item.id}>
            <TableCell className="pl-4">
              <Badge variant="secondary">{item.code}</Badge>
            </TableCell>
            <TableCell>
              <DiscrepancySeverityBadge severity={item.severity} />
            </TableCell>
            <TableCell>
              <Badge variant={item.status === "RESOLVED" ? "success" : "outline"}>
                {item.status}
              </Badge>
            </TableCell>
            <TableCell className="max-w-[360px]">
              <p className="text-[11px] text-mist-200">{item.title}</p>
              <p className="mt-0.5 text-[10px] leading-relaxed text-mist-600">{item.detail}</p>
            </TableCell>
            <TableCell>
              <Link
                href={`/finance/reconciliation/${item.run_id}`}
                className="font-mono text-[10px] text-accent-200 hover:text-accent-100"
              >
                Open run
              </Link>
            </TableCell>
            <TableCell className="text-[10px] text-mist-600">
              {formatDate(item.created_at)}
            </TableCell>
            <TableCell className="pr-4">
              {item.resolution_notes ? (
                <p className="max-w-[220px] text-[10px] text-jade-400">{item.resolution_notes}</p>
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
