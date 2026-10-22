import Link from "next/link";

import { ReconciliationOverview } from "@/components/finance/reconciliation-overview";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { serverGet } from "@/lib/api/server";
import { loadSession } from "@/lib/auth/session";
import type { FinanceStatus } from "@/lib/finance/types";
import type { ReconciliationList, ReconciliationRun } from "@/lib/finance/reconciliation";
import type { SalesOrderList } from "@/lib/operations/types";

export const dynamic = "force-dynamic";
export const metadata = { title: "Reconciliation" };

const PAGE_SIZE = 25;

interface SearchParams {
  currency?: string;
  order_id?: string;
  status?: string;
  offset?: string;
}

function errorAlert(
  title: string,
  result: { code: string; message: string; requestId: string | null },
) {
  return (
    <Alert variant="danger" title={title}>
      <span>{result.message}</span>
      <span className="mt-1 block font-mono text-[10px] text-mist-500">
        {result.code}
        {result.requestId ? ` · request ${result.requestId}` : ""}
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
  const params = await searchParams;
  const permissions = state.session.session.company?.permissions ?? [];
  const csrfToken = state.session.session.csrf_token;

  const statusResult = await serverGet<FinanceStatus>("/finance/status");
  if (!statusResult.ok) {
    return (
      <div className="mx-auto max-w-[1360px] space-y-4">
        <PageHeader
          eyebrow="Finance · Stage 5D"
          title="Reconciliation"
          description="Evidence-based reconciliation between Commerce and Finance."
          back={{ href: "/finance", label: "Finance" }}
        />
        {errorAlert("Finance status unavailable", statusResult)}
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
          eyebrow="Finance · Stage 5D"
          title="Reconciliation"
          description="Choose one Finance currency. Commerce never aggregates currencies."
          back={{ href: "/finance", label: "Finance" }}
        />
        <Alert variant="info" title="Select a currency">
          Finance exposes {currencies.join(", ")}. Open one currency explicitly:
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
        eyebrow="Finance · Stage 5D"
        back={{ href: "/finance", label: "Finance" }}
        meta={
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="secondary">Evidence reconciliation</Badge>
            <Badge variant="outline">Read-only Finance</Badge>
          </div>
        }
        title="Reconciliation"
        description="Accepted orders, purchase commitments, recorded operational costs and Finance source evidence — kept separate, with human verification only."
        actions={
          <div className="flex flex-wrap gap-2">
            <Button asChild size="sm" variant="outline">
              <Link href="/finance/discrepancies">Discrepancies</Link>
            </Button>
            <Button asChild size="sm" variant="ghost">
              <Link href="/finance">Finance ledger</Link>
            </Button>
          </div>
        }
      />

      {!listResult.ok ? errorAlert("Reconciliation runs unavailable", listResult) : null}
      {!orderResult.ok
        ? errorAlert("Accepted orders unavailable; run creation is disabled", orderResult)
        : null}
      {latestResult && !latestResult.ok
        ? errorAlert("Latest run detail unavailable", latestResult)
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
