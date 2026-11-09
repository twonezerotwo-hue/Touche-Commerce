import Link from "next/link";

import { ReconciliationDetail } from "@/components/finance/reconciliation-detail";
import { ReconciliationStatusBadge } from "@/components/finance/reconciliation-status-badge";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { serverGet } from "@/lib/api/server";
import { loadSession } from "@/lib/auth/session";
import type { ReconciliationRun } from "@/lib/finance/reconciliation";
import { getServerT, titleFor } from "@/lib/i18n/server";
import { formatTimestamp } from "@/lib/trade/format";

export const dynamic = "force-dynamic";
export const generateMetadata = () => titleFor("recTitle");

export default async function ReconciliationRunPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;
  const { t, locale } = await getServerT();
  const { id } = await params;
  const result = await serverGet<ReconciliationRun>(`/finance/reconciliation/runs/${id}`);
  if (!result.ok) {
    return (
      <div className="mx-auto max-w-[1240px] space-y-4">
        <PageHeader
          eyebrow={t("finEyebrowRecShort")}
          back={{ href: "/finance/reconciliation", label: t("finBackReconciliation") }}
          title={t("recRunUnavailable")}
        />
        <Alert variant="danger" title={t("recRunLoadFailed")}>
          {result.message}
          <span className="mt-1 block font-mono text-[10px] text-mist-500">{result.code}</span>
        </Alert>
      </div>
    );
  }
  const run = result.data;
  const permissions = state.session.session.company?.permissions ?? [];
  const canLink = permissions.includes("trade.write");
  const canReview = permissions.includes("finance.reconcile");

  return (
    <div className="mx-auto max-w-[1360px] space-y-5">
      <PageHeader
        eyebrow={t("finEyebrowRecRun")}
        back={{ href: "/finance/reconciliation", label: t("finBackReconciliation") }}
        meta={
          <div className="flex flex-wrap items-center gap-2">
            <ReconciliationStatusBadge status={run.status} />
            <Badge variant="outline">v{run.version}</Badge>
            <span className="font-mono text-[10px] text-mist-600">
              {formatTimestamp(run.created_at, locale)}
            </span>
          </div>
        }
        title={run.order_number}
        description={t("recRunDescription", {
          customer: run.customer_name,
          currency: run.currency,
          financeCurrency: run.finance_currency,
        })}
        actions={
          <div className="flex flex-wrap gap-2">
            <Button asChild size="sm" variant="outline">
              <Link href={`/finance/orders/${run.sales_order_id}`}>{t("finOrderFinanceView")}</Link>
            </Button>
            <Button asChild size="sm" variant="ghost">
              <Link href={`/orders/${run.sales_order_id}`}>{t("finCommerceOrder")}</Link>
            </Button>
          </div>
        }
      />
      <ReconciliationDetail
        run={run}
        csrfToken={state.session.session.csrf_token}
        canLink={canLink}
        canReview={canReview}
      />
    </div>
  );
}
