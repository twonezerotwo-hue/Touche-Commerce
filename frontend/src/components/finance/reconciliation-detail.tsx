import Link from "next/link";
import { Link2, LockKeyhole, ScrollText, ShieldCheck } from "lucide-react";

import {
  DiscrepancyResolutionForm,
  EvidenceLinkPanel,
  ReviewPanel,
} from "@/components/finance/reconciliation-actions";
import {
  ClassificationBadge,
  DiscrepancySeverityBadge,
} from "@/components/finance/reconciliation-status-badge";
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
import type { ReconciliationDiscrepancy, ReconciliationRun } from "@/lib/finance/reconciliation";
import { formatDate, formatTimestamp } from "@/lib/trade/format";

function FinanceObservedSummary({ run }: { run: ReconciliationRun }) {
  const summary = run.finance_snapshot.summary as
    { balances?: Record<string, { amount?: string }> } | undefined;
  const balances = summary?.balances ?? {};
  const receivable = balances.receivables?.amount ?? null;
  const payable = balances.payables?.amount ?? null;
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <div className="panel-inset p-3">
        <p className="eyebrow">Finance observed receivables</p>
        <p className="mt-1 font-mono text-[13px] text-mist-100">
          {formatReconciliationMoney(receivable, run.finance_currency, "Not reported")}
        </p>
        <p className="mt-1 text-[10px] text-mist-600">
          Company-wide ledger value. Not attributed to this order.
        </p>
      </div>
      <div className="panel-inset p-3">
        <p className="eyebrow">Finance observed payables</p>
        <p className="mt-1 font-mono text-[13px] text-mist-100">
          {formatReconciliationMoney(payable, run.finance_currency, "Not reported")}
        </p>
        <p className="mt-1 text-[10px] text-mist-600">
          Company-wide ledger value. Not attributed to this order.
        </p>
      </div>
    </div>
  );
}

function DiscrepancyCard({
  discrepancy,
  run,
  csrfToken,
  canReview,
}: {
  discrepancy: ReconciliationDiscrepancy;
  run: ReconciliationRun;
  csrfToken: string;
  canReview: boolean;
}) {
  return (
    <div className="panel-inset p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-[12px] font-medium text-mist-100">{discrepancy.title}</p>
            <Badge variant={discrepancy.status === "RESOLVED" ? "success" : "outline"}>
              {discrepancy.status}
            </Badge>
          </div>
          <p className="mt-1 text-[11px] leading-relaxed text-mist-500">{discrepancy.detail}</p>
        </div>
        <div className="flex items-center gap-2">
          <DiscrepancySeverityBadge severity={discrepancy.severity} />
          <Badge variant="secondary">{discrepancy.code}</Badge>
        </div>
      </div>
      {Object.keys(discrepancy.observed).length > 0 ? (
        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          <div className="rounded border border-white/[0.06] p-2">
            <p className="eyebrow">Expected</p>
            <pre className="mt-1 overflow-x-auto font-mono text-[10px] text-mist-400">
              {JSON.stringify(discrepancy.expected, null, 2)}
            </pre>
          </div>
          <div className="rounded border border-white/[0.06] p-2">
            <p className="eyebrow">Observed</p>
            <pre className="mt-1 overflow-x-auto font-mono text-[10px] text-mist-400">
              {JSON.stringify(discrepancy.observed, null, 2)}
            </pre>
          </div>
        </div>
      ) : null}
      {discrepancy.resolution_notes ? (
        <p className="mt-2 text-[10.5px] text-jade-400">
          Resolved {formatTimestamp(discrepancy.resolved_at ?? null)}:{" "}
          {discrepancy.resolution_notes}
        </p>
      ) : null}
      <DiscrepancyResolutionForm
        discrepancy={discrepancy}
        csrfToken={csrfToken}
        canReview={canReview}
      />
      {discrepancy.status === "OPEN" && run.status === "VERIFIED" ? (
        <p className="mt-2 text-[10px] text-mist-600">Verified run; no open item expected.</p>
      ) : null}
    </div>
  );
}

export function ReconciliationDetail({
  run,
  csrfToken,
  canLink,
  canReview,
}: {
  run: ReconciliationRun;
  csrfToken: string;
  canLink: boolean;
  canReview: boolean;
}) {
  const currency = run.currency;
  const metrics = run.metrics;
  const limitations = run.limitations;
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat
          label="Accepted order"
          value={formatReconciliationMoney(metrics.accepted_sales_order_value, currency)}
          detail={<ClassificationBadge value={run.classifications.accepted_sales_order_value} />}
        />
        <Stat
          label="Commitments"
          value={formatReconciliationMoney(metrics.purchase_commitments_total, currency)}
          detail={<ClassificationBadge value={run.classifications.purchase_commitments_total} />}
          tone="amber"
        />
        <Stat
          label="Estimated landed cost"
          value={formatReconciliationMoney(metrics.estimated_landed_cost, currency)}
          detail={<ClassificationBadge value={run.classifications.estimated_landed_cost} />}
        />
        <Stat
          label="Recorded costs"
          value={formatReconciliationMoney(metrics.recorded_operational_costs, currency)}
          detail={<ClassificationBadge value={run.classifications.recorded_operational_costs} />}
        />
        <Stat
          label="Estimate vs recorded"
          value={formatReconciliationMoney(metrics.estimate_vs_recorded_variance, currency)}
          detail={<ClassificationBadge value={run.classifications.estimate_vs_recorded_variance} />}
          tone="neutral"
        />
        <Stat
          label="Commitment-based margin"
          value={formatReconciliationMoney(metrics.commitment_based_margin, currency)}
          detail={
            <span>
              <ClassificationBadge value={run.classifications.commitment_based_margin} /> ·{" "}
              {formatReconciliationPercent(metrics.commitment_based_margin_pct)}
            </span>
          }
          tone="jade"
        />
        <Stat
          label="Document-supported margin"
          value="Not available"
          detail={<ClassificationBadge value={run.classifications.document_supported_margin} />}
          tone="neutral"
        />
        <Stat
          label="Commerce completeness"
          value={formatReconciliationPercent(metrics.completeness_score)}
          detail={`${run.evidence_count} evidence link${run.evidence_count === 1 ? "" : "s"}`}
          share={Number.parseFloat(metrics.completeness_score)}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardHeading>
              <CardTitle>Link Finance evidence</CardTitle>
              <CardDescription>
                Only transaction-level Finance aging source ids are eligible. Company-wide summary
                balances never identify this order.
              </CardDescription>
            </CardHeading>
            <Link2 className="size-4 text-mist-500" aria-hidden />
          </CardHeader>
          <CardContent>
            <EvidenceLinkPanel run={run} csrfToken={csrfToken} canLink={canLink} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardHeading>
              <CardTitle>Financial review</CardTitle>
              <CardDescription>
                Verification is a human decision recorded with reviewer identity and notes.
              </CardDescription>
            </CardHeading>
            <ShieldCheck className="size-4 text-mist-500" aria-hidden />
          </CardHeader>
          <CardContent>
            <ReviewPanel run={run} csrfToken={csrfToken} canReview={canReview} />
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card variant="inset">
          <CardHeader>
            <CardHeading>
              <CardTitle>Finance observations</CardTitle>
              <CardDescription>
                Snapshot {formatTimestamp(run.created_at)} · Finance company{" "}
                {run.finance_company_id}
              </CardDescription>
            </CardHeading>
          </CardHeader>
          <CardContent className="space-y-3">
            <FinanceObservedSummary run={run} />
            <p className="text-[10.5px] leading-relaxed text-mist-500">
              Finance data-through {formatDate(run.data_through ?? null)} · {run.finance_currency}{" "}
              source label · run currency {currency}. The labels alias, never convert.
            </p>
          </CardContent>
        </Card>
        <Card variant="inset">
          <CardHeader>
            <CardHeading>
              <CardTitle>Run controls</CardTitle>
              <CardDescription>
                Snapshot version {run.version} · {run.calculation_version}
              </CardDescription>
            </CardHeading>
            <LockKeyhole className="size-4 text-mist-500" aria-hidden />
          </CardHeader>
          <CardContent className="space-y-2 text-[11px] text-mist-400">
            <p>
              As of {formatDate(run.as_of)} · status {run.status}
            </p>
            <p>
              Finance source {run.finance_currency}; run currency {currency}. One currency, no
              aggregation.
            </p>
            <div className="flex flex-wrap gap-2">
              <Button asChild size="xs" variant="outline">
                <Link href={`/finance/orders/${run.sales_order_id}`}>Order finance view</Link>
              </Button>
              <Button asChild size="xs" variant="ghost">
                <Link href={`/orders/${run.sales_order_id}`}>Commerce order</Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="panel overflow-hidden">
        <div className="px-4 py-3">
          <p className="eyebrow">Finance source references</p>
          <p className="mt-1 text-[11px] text-mist-500">
            Stable ids from the exposed contract. A free-text counterparty is display context only.
          </p>
        </div>
        <div className="hairline" />
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-4">Type</TableHead>
              <TableHead>Source id</TableHead>
              <TableHead className="text-right">Observed amount</TableHead>
              <TableHead>Transaction level</TableHead>
              <TableHead>Hash</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {run.source_references.map((reference) => (
              <TableRow key={reference.id}>
                <TableCell className="pl-4 text-[10.5px] text-mist-400 uppercase">
                  {reference.source_type.replaceAll("_", " ")}
                </TableCell>
                <TableCell className="font-mono text-[11px] text-mist-200">
                  {reference.source_reference}
                </TableCell>
                <TableCell className="text-right font-mono text-[11px]">
                  {formatReconciliationMoney(reference.observed_amount, currency)}
                </TableCell>
                <TableCell>
                  <Badge variant={reference.is_transaction_level ? "success" : "outline"}>
                    {reference.is_transaction_level ? "ELIGIBLE" : "COMPANY-WIDE"}
                  </Badge>
                </TableCell>
                <TableCell className="font-mono text-[9.5px] text-mist-600">
                  {reference.content_hash.slice(0, 16)}…
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <div className="panel overflow-hidden">
        <div className="px-4 py-3">
          <p className="eyebrow">Evidence links</p>
          <p className="mt-1 text-[11px] text-mist-500">
            Each link is explicit, amount-checked and unique per Finance source id.
          </p>
        </div>
        <div className="hairline" />
        {run.evidence_links.length === 0 ? (
          <EmptyState
            title="No evidence linked"
            description="The run stays UNMATCHED until an operator links a supported source id and a reviewer confirms it."
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-4">Commerce entity</TableHead>
                <TableHead>Finance source</TableHead>
                <TableHead className="text-right">Amount</TableHead>
                <TableHead>Verification</TableHead>
                <TableHead>Created</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {run.evidence_links.map((evidence) => (
                <TableRow key={evidence.id}>
                  <TableCell className="pl-4 font-mono text-[10.5px] text-mist-300">
                    {evidence.source_entity_type}
                    <span className="block text-[9.5px] text-mist-600">
                      {evidence.source_entity_id}
                    </span>
                  </TableCell>
                  <TableCell className="font-mono text-[10.5px] text-mist-200">
                    {evidence.finance_source_type}
                    <span className="block text-[9.5px] text-mist-600">
                      {evidence.finance_source_reference}
                    </span>
                  </TableCell>
                  <TableCell className="text-right font-mono text-[11px]">
                    {formatReconciliationMoney(evidence.amount, currency)}
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant={evidence.verification_status === "VERIFIED" ? "success" : "outline"}
                    >
                      {evidence.verification_status}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-[10px] text-mist-600">
                    {formatTimestamp(evidence.created_at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>

      <div className="panel p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="eyebrow flex items-center gap-1.5">
            <ScrollText className="size-3" aria-hidden /> Discrepancies
          </p>
          <Badge variant={run.blocking_discrepancy_count > 0 ? "danger" : "outline"}>
            {run.open_discrepancy_count} open · {run.blocking_discrepancy_count} blocking
          </Badge>
        </div>
        <div className="mt-3 space-y-2">
          {run.discrepancies.length === 0 ? (
            <p className="text-[11px] text-mist-500">No discrepancies were generated.</p>
          ) : (
            run.discrepancies.map((discrepancy) => (
              <DiscrepancyCard
                key={discrepancy.id}
                discrepancy={discrepancy}
                run={run}
                csrfToken={csrfToken}
                canReview={canReview}
              />
            ))
          )}
        </div>
      </div>

      <div className="panel p-4">
        <p className="eyebrow">Review timeline</p>
        {run.reviews.length === 0 ? (
          <p className="mt-2 text-[11px] text-mist-500">No financial review has been recorded.</p>
        ) : (
          <ul className="mt-3 space-y-2">
            {run.reviews.map((review) => (
              <li key={review.id} className="panel-inset p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-[11px] text-mist-200">
                    {review.decision} · {review.previous_status} → {review.new_status}
                  </span>
                  <span className="text-[10px] text-mist-600">
                    {review.reviewer_name ?? review.reviewer_id} ·{" "}
                    {formatTimestamp(review.created_at)}
                  </span>
                </div>
                <p className="mt-1 text-[11px] text-mist-400">{review.notes}</p>
              </li>
            ))}
          </ul>
        )}
      </div>

      <Alert variant="info" title="Interpretation limits">
        <ul className="list-disc space-y-1 pl-4">
          {limitations.map((limitation) => (
            <li key={limitation}>{limitation}</li>
          ))}
        </ul>
      </Alert>
    </div>
  );
}
