"use client";

import { Badge } from "@/components/ui/badge";
import { useLocale } from "@/lib/i18n/locale-provider";
import type { MessageKey } from "@/lib/i18n/messages";
import { statusTone } from "@/lib/trade/format";
import type { DealStatus } from "@/lib/trade/types";

const STATUS_KEY: Record<DealStatus, MessageKey> = {
  DRAFT: "dealStatusDraft",
  OPEN: "dealStatusOpen",
  NEGOTIATION: "dealStatusNegotiation",
  WON: "dealStatusWon",
  LOST: "dealStatusLost",
  CANCELLED: "dealStatusCancelled",
};

/** One place that decides how a deal status is labelled (in the reader's language) and coloured. */
export function DealStatusBadge({ status }: { status: DealStatus }) {
  const { t } = useLocale();
  const key = STATUS_KEY[status];
  return <Badge variant={statusTone(status)}>{key ? t(key) : status}</Badge>;
}
