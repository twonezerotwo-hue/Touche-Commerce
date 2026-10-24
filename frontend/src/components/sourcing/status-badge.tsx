"use client";

import { Badge } from "@/components/ui/badge";
import { useLocale } from "@/lib/i18n/locale-provider";
import { sourcingStatusText } from "@/lib/i18n/value-labels";
import { statusTone } from "@/lib/sourcing/format";

/** One place that decides how any sourcing status is labelled and coloured. */
export function SourcingStatusBadge({ status }: { status: string }) {
  const { t } = useLocale();
  return <Badge variant={statusTone(status)}>{sourcingStatusText(t, status)}</Badge>;
}
