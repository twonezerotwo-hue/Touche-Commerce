"use client";

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
import { useLocale } from "@/lib/i18n/locale-provider";
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
  const { t, locale } = useLocale();
  const metrics = latest?.metrics;
  const financeConnected = status.state === "connected" || status.state === "degraded";
  const money = (value: string | null | undefined, unavailable?: string): string =>
    formatReconciliationMoney(value, currency, unavailable ?? t("finNotAvailable"), locale);

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat
          label={t("recAcceptedValue")}
          value={money(metrics?.accepted_sales_order_value, t("recRunFirst"))}
          detail={t("recAcceptedDetail")}
          icon={<ClipboardCheck className="size-4" aria-hidden />}
        />
        <Stat
          label={t("recCommitments")}
          value={money(metrics?.purchase_commitments_total)}
          detail={t("recCommitmentsDetail")}
          icon={<Coins className="size-4" aria-hidden />}
          tone="amber"
        />
        <Stat
          label={t("recDocumentedCosts")}
          value={money(metrics?.recorded_operational_costs)}
          detail={t("recDocumentedCostsDetail")}
          icon={<Banknote className="size-4" aria-hidden />}
        />
        <Stat
          label={t("recCommitmentMargin")}
          value={money(metrics?.commitment_based_margin)}
          detail={t("recCommitmentMarginDetail")}
          icon={<Scale className="size-4" aria-hidden />}
          tone="jade"
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
        <Card>
          <CardHeader>
            <CardHeading>
              <div className="flex flex-wrap items-center gap-2">
                <CardTitle>{t("recBoundary")}</CardTitle>
                <FinanceStatusBadge state={status.state} />
              </div>
              <CardDescription>{t("recBoundaryBody")}</CardDescription>
            </CardHeading>
          </CardHeader>
          <CardContent className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
            <div>
              <p className="eyebrow flex items-center gap-1.5">
                <Database className="size-3" aria-hidden /> {t("recSourceThrough")}
              </p>
              <p className="mt-1 text-[12.5px] text-mist-200">
                {formatDate(latest?.data_through ?? status.data_through ?? null, locale)}
              </p>
              <p className="mt-0.5 text-[10px] text-mist-600">{t("recWatermarkNote")}</p>
            </div>
            <div>
              <p className="eyebrow">{t("recCompleteness")}</p>
              <p className="mt-1 font-mono text-[12.5px] text-mist-200">
                {formatReconciliationPercent(
                  metrics?.completeness_score,
                  t("finNotAvailable"),
                  locale,
                )}
              </p>
              <p className="mt-0.5 text-[10px] text-mist-600">{t("recCompletenessNote")}</p>
            </div>
            <div>
              <p className="eyebrow">{t("recOpenDiscrepancies")}</p>
              <p className="mt-1 text-[12.5px] text-mist-200">
                {t("recOpenBlocking", {
                  open: list.open_discrepancy_count,
                  blocking: list.blocking_discrepancy_count,
                })}
              </p>
              <p className="mt-0.5 text-[10px] text-mist-600">{t("recOnlyBlocking")}</p>
            </div>
            <div>
              <p className="eyebrow">{t("recRunsInCurrency")}</p>
              <p className="mt-1 text-[12.5px] text-mist-200">{list.total}</p>
              <p className="mt-0.5 text-[10px] text-mist-600">{t("recOneCurrencyRun")}</p>
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
              {t("recNeedsWrite")}
            </CardContent>
          </Card>
        )}
      </div>

      <div className="panel overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div>
            <p className="eyebrow">{t("recRunsTitle")}</p>
            <p className="mt-1 text-[11px] text-mist-500">{t("recRunsNote")}</p>
          </div>
          <Button asChild variant="outline" size="sm">
            <Link href="/finance/discrepancies">{t("recOpenQueue")}</Link>
          </Button>
        </div>
        <div className="hairline" />
        {list.items.length === 0 ? (
          <EmptyState
            icon={<FileWarning className="size-5" aria-hidden />}
            title={t("recNoRunsTitle")}
            description={t("recNoRunsBody")}
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-4">{t("recColOrder")}</TableHead>
                <TableHead>{t("recColStatus")}</TableHead>
                <TableHead>{t("recColAsOf")}</TableHead>
                <TableHead>{t("recColFinanceThrough")}</TableHead>
                <TableHead className="text-right">{t("recColEvidence")}</TableHead>
                <TableHead className="text-right">{t("recColOpen")}</TableHead>
                <TableHead>{t("recColCreated")}</TableHead>
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
                    {formatDate(run.as_of, locale)}
                  </TableCell>
                  <TableCell className="font-mono text-[10.5px] text-mist-400">
                    {formatDate(run.data_through ?? null, locale)}
                  </TableCell>
                  <TableCell className="text-right font-mono text-[11px]">
                    {run.evidence_count}
                  </TableCell>
                  <TableCell className="text-right">
                    <Badge variant={run.blocking_discrepancy_count > 0 ? "danger" : "outline"}>
                      {run.blocking_discrepancy_count > 0
                        ? t("recOpenWithBlocking", {
                            open: run.open_discrepancy_count,
                            blocking: run.blocking_discrepancy_count,
                          })
                        : run.open_discrepancy_count}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-[10.5px] whitespace-nowrap text-mist-600">
                    {formatTimestamp(run.created_at, locale)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>

      <Alert variant="info" title={t("recMeaningTitle")}>
        {t("recMeaningPre")} <strong>{t("recMeaningStrong")}</strong> {t("recMeaningPost")}
      </Alert>
    </div>
  );
}
