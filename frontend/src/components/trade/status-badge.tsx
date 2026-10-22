import { Badge } from "@/components/ui/badge";
import { statusLabel, statusTone } from "@/lib/trade/format";
import type { DealStatus } from "@/lib/trade/types";

/** One place that decides how a deal status is labelled and coloured. */
export function DealStatusBadge({ status }: { status: DealStatus }) {
  return <Badge variant={statusTone(status)}>{statusLabel(status)}</Badge>;
}
