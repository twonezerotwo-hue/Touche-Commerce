import { Badge } from "@/components/ui/badge";
import { financeStateLabel, financeStateTone, type FinanceStatus } from "@/lib/finance/types";

/** One place that decides how a Finance connection state is labelled. */
export function FinanceStatusBadge({ state }: { state: FinanceStatus["state"] }) {
  return (
    <Badge variant={financeStateTone(state)} dot>
      {financeStateLabel(state)}
    </Badge>
  );
}
