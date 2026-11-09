"use client";

import { Badge } from "@/components/ui/badge";
import { financeStateTone, type FinanceStatus } from "@/lib/finance/types";
import { useLocale } from "@/lib/i18n/locale-provider";
import { financeStateText } from "@/lib/i18n/value-labels";

/** One place that decides how a Finance connection state is labelled. */
export function FinanceStatusBadge({ state }: { state: FinanceStatus["state"] }) {
  const { t } = useLocale();
  return (
    <Badge variant={financeStateTone(state)} dot>
      {financeStateText(t, state)}
    </Badge>
  );
}
