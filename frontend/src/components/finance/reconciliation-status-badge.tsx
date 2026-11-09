"use client";

import { Badge } from "@/components/ui/badge";
import {
  discrepancyTone,
  reconciliationStatusTone,
  type ReconciliationDiscrepancy,
  type ReconciliationRun,
} from "@/lib/finance/reconciliation";
import { useLocale } from "@/lib/i18n/locale-provider";
import {
  classificationText,
  discrepancyStatusText,
  reconciliationStatusText,
  severityText,
} from "@/lib/i18n/value-labels";

export function ReconciliationStatusBadge({ status }: { status: ReconciliationRun["status"] }) {
  const { t } = useLocale();
  return (
    <Badge variant={reconciliationStatusTone(status)} dot>
      {reconciliationStatusText(t, status)}
    </Badge>
  );
}

export function DiscrepancySeverityBadge({
  severity,
}: {
  severity: ReconciliationDiscrepancy["severity"];
}) {
  const { t } = useLocale();
  return <Badge variant={discrepancyTone(severity)}>{severityText(t, severity)}</Badge>;
}

/** OPEN / RESOLVED / DISMISSED, shown as words. */
export function DiscrepancyStatusBadge({
  status,
}: {
  status: ReconciliationDiscrepancy["status"];
}) {
  const { t } = useLocale();
  return (
    <Badge variant={status === "RESOLVED" ? "success" : "outline"}>
      {discrepancyStatusText(t, status)}
    </Badge>
  );
}

/**
 * ESTIMATED, COMMITTED, DOCUMENTED, FINANCE OBSERVED, VERIFIED or UNAVAILABLE. The tone follows the
 * stored classification, not the translated word, so the meaning cannot drift with the language.
 */
export function ClassificationBadge({ value }: { value: string | undefined }) {
  const { t } = useLocale();
  return (
    <Badge
      variant={
        value === "VERIFIED"
          ? "success"
          : value === "UNAVAILABLE"
            ? "outline"
            : value === "ESTIMATED"
              ? "warning"
              : "default"
      }
    >
      {classificationText(t, value)}
    </Badge>
  );
}
