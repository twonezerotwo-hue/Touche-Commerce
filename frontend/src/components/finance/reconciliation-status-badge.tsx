import { Badge } from "@/components/ui/badge";
import {
  discrepancyTone,
  reconciliationStatusLabel,
  reconciliationStatusTone,
  type ReconciliationDiscrepancy,
  type ReconciliationRun,
} from "@/lib/finance/reconciliation";

export function ReconciliationStatusBadge({ status }: { status: ReconciliationRun["status"] }) {
  return (
    <Badge variant={reconciliationStatusTone(status)} dot>
      {reconciliationStatusLabel(status)}
    </Badge>
  );
}

export function DiscrepancySeverityBadge({
  severity,
}: {
  severity: ReconciliationDiscrepancy["severity"];
}) {
  return <Badge variant={discrepancyTone(severity)}>{severity}</Badge>;
}

export function ClassificationBadge({ value }: { value: string | undefined }) {
  const label =
    value === "FINANCE_OBSERVED"
      ? "FINANCE OBSERVED"
      : value === "VERIFIED"
        ? "VERIFIED"
        : value === "COMMITTED"
          ? "COMMITTED"
          : value === "DOCUMENTED"
            ? "DOCUMENTED"
            : value === "ESTIMATED"
              ? "ESTIMATED"
              : "UNAVAILABLE";
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
      {label}
    </Badge>
  );
}
