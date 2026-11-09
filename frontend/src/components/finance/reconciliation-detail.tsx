"use client";

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
  DiscrepancyStatusBadge,
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
import { useLocale } from "@/lib/i18n/locale-provider";
import {
  discrepancyCodeText,
  financeSourceTypeText,
  operationsStatusText,
  reconciliationStatusText,
  reviewDecisionText,
} from "@/lib/i18n/value-labels";
import { formatDate, formatTimestamp } from "@/lib/trade/format";

function FinanceObservedSummary({ run }: { run: ReconciliationRun }) {
  const { t, locale } = useLocale();
  const summary = run.finance_snapshot.summary as
    { balances?: Record<string, { amount?: string }> } | undefined;
  const balances = summary?.balances ?? {};
  const receivable = balances.receivables?.amount ?? null;
  const payable = balances.payables?.amount ?? null;
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <div className="panel-inset p-3">
        <p className="eyebrow">{t("recFinObservedReceivables")}</p>
        <p className="mt-1 font-mono text-[13px] text-mist-100">
          {formatReconciliationMoney(receivable, run.finance_currency, t("finNotReported"), locale)}
        </p>
        <p className="mt-1 text-[10px] text-mist-600">{t("recCompanyWide")}</p>
      </div>
      <div className="panel-inset p-3">
        <p className="eyebrow">{t("recFinObservedPayables")}</p>
        <p className="mt-1 font-mono text-[13px] text-mist-100">
          {formatReconciliationMoney(payable, run.finance_currency, t("finNotReported"), locale)}
        </p>
        <p className="mt-1 text-[10px] text-mist-600">{t("recCompanyWide")}</p>
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
  const { t, locale } = useLocale();
  return (
    <div className="panel-inset p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-[12px] font-medium text-mist-100">{discrepancy.title}</p>
            <DiscrepancyStatusBadge status={discrepancy.status} />
          </div>
          <p className="mt-1 text-[11px] leading-relaxed text-mist-500">{discrepancy.detail}</p>
        </div>
        <div className="flex items-center gap-2">
          <DiscrepancySeverityBadge severity={discrepancy.severity} />
          <Badge variant="secondary">{discrepancyCodeText(t, discrepancy.code)}</Badge>
        </div>
      </div>
      {Object.keys(discrepancy.observed).length > 0 ? (
        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          <div className="rounded border border-white/[0.06] p-2">
            <p className="eyebrow">{t("recExpected")}</p>
            <pre className="mt-1 overflow-x-auto font-mono text-[10px] text-mist-400">
              {JSON.stringify(discrepancy.expected, null, 2)}
            </pre>
          </div>
          <div className="rounded border border-white/[0.06] p-2">
            <p className="eyebrow">{t("recObserved")}</p>
            <pre className="mt-1 overflow-x-auto font-mono text-[10px] text-mist-400">
              {JSON.stringify(discrepancy.observed, null, 2)}
            </pre>
          </div>
        </div>
      ) : null}
      {discrepancy.resolution_notes ? (
        <p className="mt-2 text-[10.5px] text-jade-400">
          {t("recResolvedAt", {
            time: formatTimestamp(discrepancy.resolved_at ?? null, locale),
            notes: discrepancy.resolution_notes,
          })}
        </p>
      ) : null}
      <DiscrepancyResolutionForm
        discrepancy={discrepancy}
        csrfToken={csrfToken}
        canReview={canReview}
      />
      {discrepancy.status === "OPEN" && run.status === "VERIFIED" ? (
        <p className="mt-2 text-[10px] text-mist-600">{t("recVerifiedNoOpen")}</p>
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
  const { t, locale } = useLocale();
  const currency = run.currency;
  const metrics = run.metrics;
  const money = (value: string | null | undefined): string =>
    formatReconciliationMoney(value, currency, t("finNotAvailable"), locale);
  const percent = (value: string | null | undefined): string =>
    formatReconciliationPercent(value, t("finNotAvailable"), locale);
  const limitations = run.limitations;
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat
          label={t("recStatAccepted")}
          value={money(metrics.accepted_sales_order_value)}
          detail={<ClassificationBadge value={run.classifications.accepted_sales_order_value} />}
        />
        <Stat
          label={t("recStatCommitments")}
          value={money(metrics.purchase_commitments_total)}
          detail={<ClassificationBadge value={run.classifications.purchase_commitments_total} />}
          tone="amber"
        />
        <Stat
          label={t("recStatLanded")}
          value={money(metrics.estimated_landed_cost)}
          detail={<ClassificationBadge value={run.classifications.estimated_landed_cost} />}
        />
        <Stat
          label={t("recStatRecorded")}
          value={money(metrics.recorded_operational_costs)}
          detail={<ClassificationBadge value={run.classifications.recorded_operational_costs} />}
        />
        <Stat
          label={t("recStatVariance")}
          value={money(metrics.estimate_vs_recorded_variance)}
          detail={<ClassificationBadge value={run.classifications.estimate_vs_recorded_variance} />}
          tone="neutral"
        />
        <Stat
          label={t("recCommitmentMargin")}
          value={money(metrics.commitment_based_margin)}
          detail={
            <span>
              <ClassificationBadge value={run.classifications.commitment_based_margin} /> ·{" "}
              {percent(metrics.commitment_based_margin_pct)}
            </span>
          }
          tone="jade"
        />
        <Stat
          label={t("recStatDocMargin")}
          value={t("finNotAvailable")}
          detail={<ClassificationBadge value={run.classifications.document_supported_margin} />}
          tone="neutral"
        />
        <Stat
          label={t("recStatCompleteness")}
          value={percent(metrics.completeness_score)}
          detail={t(run.evidence_count === 1 ? "recEvidenceLinkOne" : "recEvidenceLinkMany", {
            count: run.evidence_count,
          })}
          share={Number.parseFloat(metrics.completeness_score)}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardHeading>
              <CardTitle>{t("recLinkTitle")}</CardTitle>
              <CardDescription>{t("recLinkBody")}</CardDescription>
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
              <CardTitle>{t("recReviewTitle")}</CardTitle>
              <CardDescription>{t("recReviewBody")}</CardDescription>
            </CardHeading>
            <ShieldCheck className="size-4 text-mist-500" aria-hidden />
          </CardHeader>
          <CardContent>
            <ReviewPanel run={run} csrfToken={csrfToken} canReview={canReview} />
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card variant="inset">
          <CardHeader>
            <CardHeading>
              <CardTitle>{t("recObservationsTitle")}</CardTitle>
              <CardDescription>
                {t("recSnapshotLine", {
                  time: formatTimestamp(run.created_at, locale),
                  id: run.finance_company_id,
                })}
              </CardDescription>
            </CardHeading>
          </CardHeader>
          <CardContent className="space-y-3">
            <FinanceObservedSummary run={run} />
            <p className="text-[10.5px] leading-relaxed text-mist-500">
              {t("recDataThroughLine", {
                date: formatDate(run.data_through ?? null, locale),
                financeCurrency: run.finance_currency,
                currency,
              })}
            </p>
          </CardContent>
        </Card>
        <Card variant="inset">
          <CardHeader>
            <CardHeading>
              <CardTitle>{t("recControlsTitle")}</CardTitle>
              <CardDescription>
                {t("recControlsLine", {
                  version: run.version,
                  calculation: run.calculation_version,
                })}
              </CardDescription>
            </CardHeading>
            <LockKeyhole className="size-4 text-mist-500" aria-hidden />
          </CardHeader>
          <CardContent className="space-y-2 text-[11px] text-mist-400">
            <p>
              {t("recAsOfLine", {
                date: formatDate(run.as_of, locale),
                status: reconciliationStatusText(t, run.status),
              })}
            </p>
            <p>{t("recCurrencyLine", { financeCurrency: run.finance_currency, currency })}</p>
            <div className="flex flex-wrap gap-2">
              <Button asChild size="xs" variant="outline">
                <Link href={`/finance/orders/${run.sales_order_id}`}>
                  {t("finOrderFinanceView")}
                </Link>
              </Button>
              <Button asChild size="xs" variant="ghost">
                <Link href={`/orders/${run.sales_order_id}`}>{t("finCommerceOrder")}</Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="panel overflow-hidden">
        <div className="px-4 py-3">
          <p className="eyebrow">{t("recSourceRefs")}</p>
          <p className="mt-1 text-[11px] text-mist-500">{t("recSourceRefsNote")}</p>
        </div>
        <div className="hairline" />
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-4">{t("recColType")}</TableHead>
              <TableHead>{t("recColSourceId")}</TableHead>
              <TableHead className="text-right">{t("recColObserved")}</TableHead>
              <TableHead>{t("recColTransactionLevel")}</TableHead>
              <TableHead>{t("recColHash")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {run.source_references.map((reference) => (
              <TableRow key={reference.id}>
                <TableCell className="pl-4 text-[10.5px] text-mist-400 uppercase">
                  {financeSourceTypeText(t, reference.source_type)}
                </TableCell>
                <TableCell className="font-mono text-[11px] text-mist-200">
                  {reference.source_reference}
                </TableCell>
                <TableCell className="text-right font-mono text-[11px]">
                  {money(reference.observed_amount)}
                </TableCell>
                <TableCell>
                  <Badge variant={reference.is_transaction_level ? "success" : "outline"}>
                    {reference.is_transaction_level ? t("recEligible") : t("recCompanyWideBadge")}
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
          <p className="eyebrow">{t("recEvidenceLinks")}</p>
          <p className="mt-1 text-[11px] text-mist-500">{t("recEvidenceLinksNote")}</p>
        </div>
        <div className="hairline" />
        {run.evidence_links.length === 0 ? (
          <EmptyState title={t("recNoEvidenceTitle")} description={t("recNoEvidenceBody")} />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-4">{t("recColEntity")}</TableHead>
                <TableHead>{t("recColFinanceSource")}</TableHead>
                <TableHead className="text-right">{t("recColAmount")}</TableHead>
                <TableHead>{t("recColVerification")}</TableHead>
                <TableHead>{t("recColCreated")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {run.evidence_links.map((evidence) => (
                <TableRow key={evidence.id}>
                  <TableCell className="pl-4 font-mono text-[10.5px] text-mist-300">
                    {evidence.source_entity_type === "SALES_ORDER"
                      ? t("entSalesOrder")
                      : evidence.source_entity_type}
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
                    {money(evidence.amount)}
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant={evidence.verification_status === "VERIFIED" ? "success" : "outline"}
                    >
                      {operationsStatusText(t, evidence.verification_status)}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-[10px] text-mist-600">
                    {formatTimestamp(evidence.created_at, locale)}
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
            <ScrollText className="size-3" aria-hidden /> {t("recDiscrepancies")}
          </p>
          <Badge variant={run.blocking_discrepancy_count > 0 ? "danger" : "outline"}>
            {t("recOpenBlocking", {
              open: run.open_discrepancy_count,
              blocking: run.blocking_discrepancy_count,
            })}
          </Badge>
        </div>
        <div className="mt-3 space-y-2">
          {run.discrepancies.length === 0 ? (
            <p className="text-[11px] text-mist-500">{t("recNoDiscrepancies")}</p>
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
        <p className="eyebrow">{t("recReviewTimeline")}</p>
        {run.reviews.length === 0 ? (
          <p className="mt-2 text-[11px] text-mist-500">{t("recNoReviews")}</p>
        ) : (
          <ul className="mt-3 space-y-2">
            {run.reviews.map((review) => (
              <li key={review.id} className="panel-inset p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-[11px] text-mist-200">
                    {reviewDecisionText(t, review.decision)} ·{" "}
                    {reconciliationStatusText(t, review.previous_status)} →{" "}
                    {reconciliationStatusText(t, review.new_status)}
                  </span>
                  <span className="text-[10px] text-mist-600">
                    {review.reviewer_name ?? review.reviewer_id} ·{" "}
                    {formatTimestamp(review.created_at, locale)}
                  </span>
                </div>
                <p className="mt-1 text-[11px] text-mist-400">{review.notes}</p>
              </li>
            ))}
          </ul>
        )}
      </div>

      <Alert variant="info" title={t("recLimitsTitle")}>
        <ul className="list-disc space-y-1 pl-4">
          {limitations.map((limitation) => (
            <li key={limitation}>{limitation}</li>
          ))}
        </ul>
      </Alert>
    </div>
  );
}
