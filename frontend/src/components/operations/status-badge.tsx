import { Badge } from "@/components/ui/badge";
import { operationsStatusLabel, operationsStatusTone } from "@/lib/operations/format";

/** One place that decides how a Stage 4 status is labelled and coloured. */
export function OperationsStatusBadge({ status }: { status: string }) {
  return <Badge variant={operationsStatusTone(status)}>{operationsStatusLabel(status)}</Badge>;
}
