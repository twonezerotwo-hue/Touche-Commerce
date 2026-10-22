import Link from "next/link";
import { Banknote, ClipboardCheck, Coins, Database, FileWarning, Scale } from "lucide-react";

import { CreateReconciliationRun } from "@/components/finance/reconciliation-actions";
import { ReconciliationStatusBadge } from "@/components/finance/reconciliation-status-badge";
import { FinanceStatusBadge } from "@/components/finance/status-badge";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardHeading,
  CardTitle,
} from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Stat } from "@/components/ui/stat";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatReconciliationMoney, formatReconciliationPercent } from "@/lib/finance/format";
import type { FinanceStatus } from "@/lib/finance/types";
import type { ReconciliationList, ReconciliationRun } from "@/lib/finance/reconciliation";
import { formatDate, formatTimestamp } from "@/lib/trade/format";

export interface OrderOption {
  id: string;
  order_number: string;
  status: string;
  currency: string;
}

export function ReconciliationOverview({
  status,
  list,
  latest,
  currency,
  orders,
  csrfToken,
  canCreate,
}: {
  status: FinanceStatus;
  list: ReconciliationList;
  latest: ReconciliationRun | null;
  currency: string;
  orders: OrderOption[];
  csrfToken: string;
  canCreate: boolean;
}) {
  const metrics = latest?.metrics;
  const financeConnected = status.state === "connected" || status.state === "degraded";

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat
          label="Accepted order value"
          value={formatReconciliationMoney(
            metrics?.accepted_sales_order_value,
            currency,
            "Run a reconciliation",
          )}
          detail="Commerce documented acceptance, not revenue recognition"
          icon={<ClipboardCheck className="size-4" aria-hidden />}
        />
        <Stat
          label="Purchase commitments"
          value={formatReconciliationMoney(metrics?.purchase_commitments_total, currency)}
          detail="Committed purchase orders only; no currency conversion"
          icon={<Coins className="size-4" aria-hidden />}
          tone="amber"
        />
        <Stat
          label="Documented operational costs"
          value={formatReconciliationMoney(metrics?.recorded_operational_costs, currency)}
          detail="Recorded shipment costs in the order currency"
          icon={<Banknote className="size-4" aria-hidden />}
        />
        <Stat
          label="Commitment-based margin"
          value={formatReconciliationMoney(metrics?.commitment_based_margin, currency)}
          detail="Operational interpretation — not accounting profit"
          icon={<Scale className="size-4" aria-hidden />}
          tone="jade"
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.35fr_1fr]">
        <Card>
          <CardHeader>
            <CardHeading>
              <div className="flex flex-wrap items-center gap-2">
                <CardTitle>Finance boundary</CardTitle>
                <FinanceStatusBadge state={status.state} />
              </div>
              <CardDescription>
                Finance is the financial source of truth. Commerce reads only summary and aging
                data; it never posts journals, invoices or payments.
              </CardDescription>
            </CardHeading>
          </CardHeader>
          <CardContent className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
            <div>
              <p className="eyebrow flex items-center gap-1.5">
                <Database className="size-3" aria-hidden /> Source data-through
              </p>
              <p className="mt-1 text-[12.5px] text-mist-200">
                {formatDate(latest?.data_through ?? status.data_through ?? null)}
              </p>
              <p className="mt-0.5 text-[10px] text-mist-600">
                Finance watermark captured in the run snapshot.
              </p>
            </div>
            <div>
              <p className="eyebrow">Evidence completeness</p>
              <p className="mt-1 font-mono text-[12.5px] text-mist-200">
                {formatReconciliationPercent(metrics?.completeness_score)}
              </p>
              <p className="mt-0.5 text-[10px] text-mist-600">
                Commerce source checks; Finance link is reviewed separately.
              </p>
            </div>
            <div>
              <p className="eyebrow">Open discrepancies</p>
              <p className="mt-1 text-[12.5px] text-mist-200">
                {list.open_discrepancy_count} open · {list.blocking_discrepancy_count} blocking
              </p>
              <p className="mt-0.5 text-[10px] text-mist-600">
                Only blocking items prevent verification.
              </p>
            </div>
            <div>
              <p className="eyebrow">Runs in this currency</p>
              <p className="mt-1 text-[12.5px] text-mist-200">{list.total}</p>
              <p className="mt-0.5 text-[10px] text-mist-600">
                One currency per run. No cross-currency total exists.
              </p>
            </div>
          </CardContent>
        </Card>

        {canCreate ? (
          <CreateReconciliationRun
            orders={orders}
            currency={currency}
            csrfToken={csrfToken}
            financeReady={financeConnected}
          />
        ) : (
          <Card variant="inset">
            <CardContent className="py-4 text-[12px] text-mist-400">
              Creating a reconciliation run requires trade.write. Finance review requires the
              separate finance.reconcile capability.
            </CardContent>
          </Card>
        )}
      </div>

      <div className="panel overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div>
            <p className="eyebrow">Reconciliation runs</p>
            <p className="mt-1 text-[11px] text-mist-500">
              Snapshots are reproducible; evidence and reviews are appended to the run.
            </p>
          </div>
          <Button asChild variant="outline" size="sm">
            <Link href="/finance/discrepancies">Open discrepancy queue</Link>
          </Button>
        </div>
        <div className="hairline" />
        {list.items.length === 0 ? (
          <EmptyState
            icon={<FileWarning className="size-5" aria-hidden />}
            title="No reconciliation runs"
            description="Create a run for an accepted order after its purchase and cost evidence exists."
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-4">Order</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>As of</TableHead>
                <TableHead>Finance through</TableHead>
                <TableHead className="text-right">Evidence</TableHead>
                <TableHead className="text-right">Open</TableHead>
                <TableHead>Created</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {list.items.map((run) => (
                <TableRow key={run.id}>
                  <TableCell className="pl-4">
                    <Link
                      href={`/finance/reconciliation/${run.id}`}
                      className="font-mono text-[11.5px] text-accent-200 hover:text-accent-100"
                    >
                      {run.order_number}
                    </Link>
                    <span className="block text-[10px] text-mist-600">{run.customer_name}</span>
                  </TableCell>
                  <TableCell>
                    <ReconciliationStatusBadge status={run.status} />
                  </TableCell>
                  <TableCell className="font-mono text-[10.5px] text-mist-400">
                    {formatDate(run.as_of)}
                  </TableCell>
                  <TableCell className="font-mono text-[10.5px] text-mist-400">
                    {formatDate(run.data_through ?? null)}
                  </TableCell>
                  <TableCell className="text-right font-mono text-[11px]">
                    {run.evidence_count}
                  </TableCell>
                  <TableCell className="text-right">
                    <Badge variant={run.blocking_discrepancy_count > 0 ? "danger" : "outline"}>
                      {run.open_discrepancy_count}
                      {run.blocking_discrepancy_count > 0
                        ? ` · ${run.blocking_discrepancy_count} blocking`
                        : ""}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-[10.5px] whitespace-nowrap text-mist-600">
                    {formatTimestamp(run.created_at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>

      <Alert variant="info" title="What these numbers mean">
        Estimated, committed, documented and Finance-observed values are deliberately distinct.
        Document-supported margin and actual profit remain <strong>Unavailable</strong> because the
        Finance contract exposes no transaction-level invoice/payment source. A reviewed match is an
        evidence decision, not an accounting entry.
      </Alert>
    </div>
  );
}
