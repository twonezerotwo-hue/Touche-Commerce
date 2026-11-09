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
import { completenessTone, type OrderIntelligenceDetail } from "@/lib/finance/intelligence";
import { completenessWord, modelWord, statusWord } from "@/lib/finance/intelligence-text";
import { getServerT, titleFor } from "@/lib/i18n/server";

export const dynamic = "force-dynamic";
export const generateMetadata = () => titleFor("oiOrderFinance");

export default async function OrderIntelligencePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;

  const { t, locale } = await getServerT();
  const { id } = await params;
  const result = await serverGet<OrderIntelligenceDetail>(
    `/finance/intelligence/orders/${encodeURIComponent(id)}`,
  );

  if (!result.ok) {
    return (
      <div className="mx-auto max-w-[1100px] space-y-4">
        <PageHeader
          eyebrow={t("intEyebrow")}
          back={{ href: "/finance/intelligence/orders", label: t("intBackOrders") }}
          title={t("oiUnavailable")}
        />
        <ApiErrorAlert title={t("oiLoadFailed")} failure={result} />
      </div>
    );
  }

  const detail = result.data;
  const order = detail.order;
  const permissions = state.session.session.company?.permissions ?? [];

  return (
    <div className="mx-auto max-w-[1360px] space-y-5">
      <PageHeader
        eyebrow={t("intEyebrow")}
        back={{ href: "/finance/intelligence/orders", label: t("intBackOrders") }}
        meta={
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline">{statusWord(t, locale, order.status)}</Badge>
            <Badge variant="secondary">{modelWord(t, locale, order.fulfilment_model)}</Badge>
            <Badge variant={completenessTone(order.completeness)}>
              {completenessWord(t, order.completeness)}
            </Badge>
            {order.reconciliation_status ? (
              <ReconciliationStatusBadge status={order.reconciliation_status} />
            ) : (
              <Badge variant="outline">{t("oiNoRun")}</Badge>
            )}
          </div>
        }
        title={order.order_number}
        description={t("oiDescription", {
          customer: order.customer_name,
          currency: order.currency,
        })}
        actions={
          <div className="flex flex-wrap gap-2">
            {order.latest_run_id ? (
              <Button asChild size="sm">
                <Link href={`/finance/reconciliation/${order.latest_run_id}`}>
                  {t("oiOpenLatest")}
                </Link>
              </Button>
            ) : null}
            <Button asChild size="sm" variant="outline">
              <Link href={`/finance/reconciliation?order_id=${order.sales_order_id}`}>
                {t("oiRunsForOrder")}
              </Link>
            </Button>
            <Button asChild size="sm" variant="outline">
              <Link href={`/finance/orders/${order.sales_order_id}`}>{t("oiOrderFinance")}</Link>
            </Button>
            <Button asChild size="sm" variant="ghost">
              <Link href={`/orders/${order.sales_order_id}`}>{t("oiCommerceOrder")}</Link>
            </Button>
          </div>
        }
      />

      <OrderFlags order={order} />

      <Alert variant="info" title={t("intNoticeTitle")}>
        {t("intNotice")}
      </Alert>

      <IntelligenceDetail
        detail={detail}
        csrfToken={state.session.session.csrf_token}
        canReview={permissions.includes("finance.reconcile")}
      />
    </div>
  );
}
