import Link from "next/link";

import { ApiErrorAlert } from "@/components/finance/api-error-alert";
import { IntelligenceDetail } from "@/components/finance/intelligence-detail";
import { OrderFlags } from "@/components/finance/intelligence-orders-table";
import { ReconciliationStatusBadge } from "@/components/finance/reconciliation-status-badge";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { serverGet } from "@/lib/api/server";
import { loadSession } from "@/lib/auth/session";
import {
  completenessTone,
  humanize,
  INTELLIGENCE_ANALYSIS_NOTICE,
  type OrderIntelligenceDetail,
} from "@/lib/finance/intelligence";

export const dynamic = "force-dynamic";
export const metadata = { title: "Order intelligence" };

export default async function OrderIntelligencePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;

  const { id } = await params;
  const result = await serverGet<OrderIntelligenceDetail>(
    `/finance/intelligence/orders/${encodeURIComponent(id)}`,
  );

  if (!result.ok) {
    return (
      <div className="mx-auto max-w-[1100px] space-y-4">
        <PageHeader
          eyebrow="Finance · Stage 5E"
          back={{ href: "/finance/intelligence/orders", label: "Order profitability" }}
          title="Order intelligence unavailable"
        />
        <ApiErrorAlert title="Could not load the order analysis" failure={result} />
      </div>
    );
  }

  const detail = result.data;
  const order = detail.order;
  const permissions = state.session.session.company?.permissions ?? [];

  return (
    <div className="mx-auto max-w-[1360px] space-y-5">
      <PageHeader
        eyebrow="Finance · Stage 5E"
        back={{ href: "/finance/intelligence/orders", label: "Order profitability" }}
        meta={
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline">{humanize(order.status)}</Badge>
            <Badge variant="secondary">{humanize(order.fulfilment_model)}</Badge>
            <Badge variant={completenessTone(order.completeness)}>{order.completeness}</Badge>
            {order.reconciliation_status ? (
              <ReconciliationStatusBadge status={order.reconciliation_status} />
            ) : (
              <Badge variant="outline">No reconciliation run</Badge>
            )}
          </div>
        }
        title={order.order_number}
        description={`${order.customer_name} · ${order.currency}. Estimated, committed and documented figures are separate bases; nothing here is an accounting entry.`}
        actions={
          <div className="flex flex-wrap gap-2">
            {order.latest_run_id ? (
              <Button asChild size="sm">
                <Link href={`/finance/reconciliation/${order.latest_run_id}`}>Open latest run</Link>
              </Button>
            ) : null}
            <Button asChild size="sm" variant="outline">
              <Link href={`/finance/reconciliation?order_id=${order.sales_order_id}`}>
                Runs for this order
              </Link>
            </Button>
            <Button asChild size="sm" variant="outline">
              <Link href={`/finance/orders/${order.sales_order_id}`}>Order finance</Link>
            </Button>
            <Button asChild size="sm" variant="ghost">
              <Link href={`/orders/${order.sales_order_id}`}>Commerce order</Link>
            </Button>
          </div>
        }
      />

      <OrderFlags order={order} />

      <Alert variant="info" title="Operational figures">
        {INTELLIGENCE_ANALYSIS_NOTICE}
      </Alert>

      <IntelligenceDetail
        detail={detail}
        csrfToken={state.session.session.csrf_token}
        canReview={permissions.includes("finance.reconcile")}
      />
    </div>
  );
}
