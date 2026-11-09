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
import type { ReconciliationDiscrepancy } from "@/lib/finance/reconciliation";
import { useLocale } from "@/lib/i18n/locale-provider";
import { discrepancyCodeText } from "@/lib/i18n/value-labels";
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
  const { t, locale } = useLocale();
  if (items.length === 0) {
    return <EmptyState embedded title={t("disNoneTitle")} description={t("disNoneBody")} />;
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="pl-4">{t("disColCode")}</TableHead>
          <TableHead>{t("disColSeverity")}</TableHead>
          <TableHead>{t("disColStatus")}</TableHead>
          <TableHead>{t("disColFinding")}</TableHead>
          <TableHead>{t("disColRun")}</TableHead>
          <TableHead>{t("disColCreated")}</TableHead>
          <TableHead className="pr-4">{t("disColResolution")}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {items.map((item) => (
          <TableRow key={item.id}>
            <TableCell className="pl-4">
              <Badge variant="secondary">{discrepancyCodeText(t, item.code)}</Badge>
            </TableCell>
            <TableCell>
              <DiscrepancySeverityBadge severity={item.severity} />
            </TableCell>
            <TableCell>
              <DiscrepancyStatusBadge status={item.status} />
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
                {t("disOpenRun")}
              </Link>
            </TableCell>
            <TableCell className="text-[10px] text-mist-600">
              {formatDate(item.created_at, locale)}
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
