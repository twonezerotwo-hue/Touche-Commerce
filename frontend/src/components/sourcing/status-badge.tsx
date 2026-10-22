import { Badge } from "@/components/ui/badge";
import { statusLabel, statusTone } from "@/lib/sourcing/format";

/** One place that decides how any sourcing status is labelled and coloured. */
export function SourcingStatusBadge({ status }: { status: string }) {
  return <Badge variant={statusTone(status)}>{statusLabel(status)}</Badge>;
}
