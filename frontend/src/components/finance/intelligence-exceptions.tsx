"use client";

import Link from "next/link";

import { DiscrepancyResolutionForm } from "@/components/finance/reconciliation-actions";
import {
  DiscrepancySeverityBadge,
  DiscrepancyStatusBadge,
} from "@/components/finance/reconciliation-status-badge";
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
import type { FinancialException } from "@/lib/finance/intelligence";
import { exceptionCodeWord } from "@/lib/finance/intelligence-text";
import { useLocale } from "@/lib/i18n/locale-provider";
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
  const { t, locale } = useLocale();
  if (items.length === 0) {
    return (
      <EmptyState
        embedded
        title={t("intNoExceptionsTitle")}
        description={t("intNoExceptionsDesc")}
      />
    );
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="pl-4">{t("intColOrder")}</TableHead>
          <TableHead>{t("intExColException")}</TableHead>
          <TableHead className="pr-4">{t("intExColFinding")}</TableHead>
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
                {item.currency} · {formatDate(item.created_at, locale)}
              </span>
            </TableCell>
            <TableCell className="min-w-[190px] align-top">
              <span className="flex flex-col items-start gap-1">
                <Badge variant="secondary">{exceptionCodeWord(t, locale, item.code)}</Badge>
                <span className="flex flex-wrap items-center gap-1">
                  <DiscrepancySeverityBadge severity={item.severity} />
                  <DiscrepancyStatusBadge status={item.status} />
                </span>
              </span>
            </TableCell>
            <TableCell className="min-w-[280px] pr-4 align-top">
              <p className="text-[11px] text-mist-200">{item.title}</p>
              <p className="mt-0.5 text-[10px] leading-relaxed text-mist-600">{item.detail}</p>
              <p className="mt-1.5 text-[10px] text-mist-500">
                {item.finance_source_reference ? (
                  <>
                    {t("intFinanceSource")}{" "}
                    <span className="font-mono text-mist-300">{item.finance_source_reference}</span>
                  </>
                ) : (
                  t("intNoFinanceReference")
                )}
                {" · "}
                <Link
                  href={`/finance/reconciliation/${item.run_id}`}
                  className="font-mono text-accent-200 hover:text-accent-100"
                >
                  {t("intOpenRun")}
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
