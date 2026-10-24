"use client";

import { Badge } from "@/components/ui/badge";
import { useLocale } from "@/lib/i18n/locale-provider";
import { operationsStatusText } from "@/lib/i18n/value-labels";
import { operationsStatusTone } from "@/lib/operations/format";

/** One place that decides how a Stage 4 status is labelled (in the reader's language) and coloured. */
export function OperationsStatusBadge({ status }: { status: string }) {
  const { t } = useLocale();
  return <Badge variant={operationsStatusTone(status)}>{operationsStatusText(t, status)}</Badge>;
}
