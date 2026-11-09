import Link from "next/link";

import { ReconciliationOverview } from "@/components/finance/reconciliation-overview";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { serverGet } from "@/lib/api/server";
import { loadSession } from "@/lib/auth/session";
import type { FinanceStatus } from "@/lib/finance/types";
import { getServerT, titleFor, type ServerTranslator } from "@/lib/i18n/server";
import type { ReconciliationList, ReconciliationRun } from "@/lib/finance/reconciliation";
import type { SalesOrderList } from "@/lib/operations/types";

export const dynamic = "force-dynamic";
export const generateMetadata = () => titleFor("recTitle");

const PAGE_SIZE = 25;

interface SearchParams {
  currency?: string;
  order_id?: string;
  status?: string;
  offset?: string;
}

function errorAlert(
  t: ServerTranslator["t"],
  title: string,
  result: { code: string; message: string; requestId: string | null },
) {
  return (
    <Alert variant="danger" title={title}>
      <span>{result.message}</span>
      <span className="mt-1 block font-mono text-[10px] text-mist-500">
        {result.code}
        {result.requestId ? ` · ${t("finRequestSuffix", { id: result.requestId })}` : ""}
      </span>
    </Alert>
  );
}

export default async function ReconciliationPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;
  const { t } = await getServerT();
  const params = await searchParams;
  const permissions = state.session.session.company?.permissions ?? [];
  const csrfToken = state.session.session.csrf_token;

  const statusResult = await serverGet<FinanceStatus>("/finance/status");
  if (!statusResult.ok) {
    return (
      <div className="mx-auto max-w-[1360px] space-y-4">
        <PageHeader
          eyebrow={t("finEyebrowRec")}
          title={t("recTitle")}
          description={t("recHintShort")}
          back={{ href: "/finance", label: t("finBackFinance") }}
        />
        {errorAlert(t, t("recStatusUnavailable"), statusResult)}
      </div>
    );
  }

  const status = statusResult.data;
  const currencies = status.available_currencies ?? [];
  const requested = (params.currency ?? "").toUpperCase();
  const currency = currencies.includes(requested)
    ? requested
    : currencies.length === 1
      ? currencies[0]
      : "";
  const offset = Math.max(0, Number.parseInt(params.offset ?? "0", 10) || 0);
  const canCreate = permissions.includes("trade.write");

  if (currencies.length > 1 && !currency) {
    return (
      <div className="mx-auto max-w-[1360px] space-y-4">
        <PageHeader
          eyebrow={t("finEyebrowRec")}
          title={t("recTitle")}
          description={t("recChooseCurrency")}
          back={{ href: "/finance", label: t("finBackFinance") }}
        />
        <Alert variant="info" title={t("recSelectCurrencyTitle")}>
          {t("recSelectCurrencyBody", { currencies: currencies.join(", ") })}
          <span className="mt-2 flex flex-wrap gap-2">
            {currencies.map((item) => (
              <Button key={item} asChild size="xs" variant="outline">
                <Link href={`/finance/reconciliation?currency=${item}`}>{item}</Link>
              </Button>
            ))}
          </span>
        </Alert>
      </div>
    );
  }

  const query = new URLSearchParams({
    limit: String(PAGE_SIZE),
    offset: String(offset),
  });
  if (currency) query.set("currency", currency);
  if (params.order_id) query.set("order_id", params.order_id);
  if (params.status) query.set("status", params.status);

  const [listResult, orderResult] = await Promise.all([
    serverGet<ReconciliationList>(`/finance/reconciliation?${query.toString()}`),
    serverGet<SalesOrderList>("/sales-orders?limit=50"),
  ]);

  const list = listResult.ok ? listResult.data : null;
  const latestId = list?.items[0]?.id;
  const latestResult = latestId
    ? await serverGet<ReconciliationRun>(`/finance/reconciliation/runs/${latestId}`)
    : null;

  const orders = (orderResult.ok ? orderResult.data.items : []).map((order) => ({
    id: order.id,
    order_number: order.order_number,
    status: order.status,
    currency: order.currency,
  }));

  return (
    <div className="mx-auto max-w-[1360px] space-y-5">
      <PageHeader
        eyebrow={t("finEyebrowRec")}
        back={{ href: "/finance", label: t("finBackFinance") }}
        meta={
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="secondary">{t("recBadgeEvidence")}</Badge>
            <Badge variant="outline">{t("recBadgeReadOnly")}</Badge>
          </div>
        }
        title={t("recTitle")}
        description={t("recDescription")}
        actions={
          <div className="flex flex-wrap gap-2">
            <Button asChild size="sm" variant="outline">
              <Link href="/finance/discrepancies">{t("finBtnDiscrepancies")}</Link>
            </Button>
            <Button asChild size="sm" variant="ghost">
              <Link href="/finance">{t("finLedgerLink")}</Link>
            </Button>
          </div>
        }
      />

      {!listResult.ok ? errorAlert(t, t("recRunsUnavailable"), listResult) : null}
      {!orderResult.ok ? errorAlert(t, t("recOrdersUnavailable"), orderResult) : null}
      {latestResult && !latestResult.ok
        ? errorAlert(t, t("recLatestUnavailable"), latestResult)
        : null}

      {list ? (
        <ReconciliationOverview
          status={status}
          list={list}
          latest={latestResult?.ok ? latestResult.data : null}
          currency={currency}
          orders={orders}
          csrfToken={csrfToken}
          canCreate={canCreate}
        />
      ) : null}
    </div>
  );
}
