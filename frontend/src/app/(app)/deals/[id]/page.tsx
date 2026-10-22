import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, History, ReceiptText } from "lucide-react";

import { DealEditForm } from "@/components/trade/deal-edit-form";
import { DealStatusBadge } from "@/components/trade/status-badge";
import { TransitionPanel } from "@/components/trade/transition-panel";
import { ConversionCard } from "@/components/operations/conversion-card";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { Stat } from "@/components/ui/stat";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { serverGet } from "@/lib/api/server";
import { loadSession } from "@/lib/auth/session";
import type {
  CustomerAcceptance,
  SalesQuoteOption,
  SalesQuoteOptionList,
} from "@/lib/operations/types";
import { formatDate, formatMoney, formatQuantity, formatTimestamp } from "@/lib/trade/format";
import type { Deal } from "@/lib/trade/types";
import { cn } from "@/lib/utils";

export const dynamic = "force-dynamic";

export default async function DealDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;

  const { id } = await params;
  const result = await serverGet<Deal>(`/deals/${id}`);
  if (!result.ok) {
    if (result.code === "NOT_FOUND") notFound();
    return (
      <div className="mx-auto max-w-[1100px] space-y-4">
        <PageHeader
          eyebrow="Deal"
          back={{ href: "/deals", label: "Deals" }}
          title="Deal unavailable"
          description="The record could not be loaded for this company."
        />
        <Alert variant="danger" title="Deal unavailable">
          {result.message}
        </Alert>
      </div>
    );
  }

  const deal = result.data;
  const session = state.session.session;
  const canWrite = session.company?.permissions.includes("trade.write") ?? false;

  const [quoteOptions, acceptances] = await Promise.all([
    serverGet<SalesQuoteOptionList>(`/sales-quotes?deal_id=${deal.id}&limit=50`),
    serverGet<{ items: CustomerAcceptance[] }>(`/deals/${deal.id}/customer-acceptance`),
  ]);
  const quotes: SalesQuoteOption[] = quoteOptions.ok ? quoteOptions.data.items : [];
  const recordedAcceptances: CustomerAcceptance[] = acceptances.ok ? acceptances.data.items : [];
  const convertible = deal.status === "OPEN" || deal.status === "NEGOTIATION";

  return (
    <div className="mx-auto max-w-[1280px] space-y-5">
      <PageHeader
        eyebrow={deal.reference}
        back={{ href: "/deals", label: "Deals" }}
        meta={
          <>
            <DealStatusBadge status={deal.status} />
            <Badge variant="outline" className="font-mono">
              v{deal.version}
            </Badge>
            {canWrite ? null : (
              <span className="text-[10px] tracking-[0.08em] text-mist-600 uppercase">
                Read-only
              </span>
            )}
          </>
        }
        title={deal.title}
        description={
          <>
            {deal.counterparty_name} · expected close {formatDate(deal.expected_close_date)} ·{" "}
            <span className="data-value">{formatMoney(deal.total_value, deal.currency)}</span>
          </>
        }
        actions={
          <Button asChild variant="outline" size="sm">
            <Link href="/deals">
              <ArrowLeft className="size-3.5" aria-hidden />
              All deals
            </Link>
          </Button>
        }
      />

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat
          label="Deal value"
          value={formatMoney(deal.total_value, deal.currency)}
          detail={`Computed from ${deal.items.length} ${deal.items.length === 1 ? "line" : "lines"}`}
          icon={<ReceiptText className="size-3.5" aria-hidden />}
        />
        <Stat
          label="Lines"
          value={deal.items.length}
          detail={`Priced in ${deal.currency}`}
          tone="neutral"
        />
        <Stat
          label="Version"
          value={deal.version}
          detail="Optimistic concurrency token"
          tone="neutral"
        />
        <Stat
          label="Created"
          value={formatDate(deal.created_at)}
          detail={formatTimestamp(deal.created_at)}
          tone="neutral"
        />
      </section>

      <section className="panel space-y-3 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <p className="eyebrow">Execution</p>
            <h2 className="mt-1 text-[14px] font-medium text-mist-100">
              {deal.status === "WON" ? "This deal is won" : "Convert to a sales order"}
            </h2>
          </div>
          <Badge variant={deal.status === "WON" ? "success" : "outline"}>
            {deal.status === "WON" ? "WON" : "Requires customer acceptance"}
          </Badge>
        </div>

        {deal.status === "WON" ? (
          <p className="text-[11.5px] text-mist-400">
            The deal already produced its sales order.{" "}
            <Link href="/orders" className="text-accent-200 hover:text-accent-100">
              Open the order register
            </Link>{" "}
            to see the frozen commercial terms and fulfilment progress.
          </p>
        ) : convertible ? (
          <ConversionCard
            dealId={deal.id}
            quotes={quotes}
            acceptances={recordedAcceptances}
            csrfToken={session.csrf_token}
            canWrite={canWrite}
          />
        ) : (
          <Alert variant="info" title="Deal not convertible">
            Only an open or negotiating deal can become an order. Move the deal to negotiation
            first.
          </Alert>
        )}
      </section>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)]">
        <div className="space-y-4">
          <div className="panel overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-3 px-5 pt-4.5 pb-3">
              <div>
                <p className="eyebrow">Commercial lines</p>
                <h2 className="mt-1.5 text-[14px] font-medium text-mist-100">
                  Products on this deal
                </h2>
              </div>
              <span className="text-[10.5px] text-mist-500">
                {deal.items.length} {deal.items.length === 1 ? "line" : "lines"} · {deal.currency}
              </span>
            </div>
            <div className="hairline" />
            <Table bare>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-5">Product</TableHead>
                  <TableHead className="text-right">Quantity</TableHead>
                  <TableHead className="text-right">Unit price</TableHead>
                  <TableHead className="pr-5 text-right">Line total</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {deal.items.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell className="pl-5">
                      <span className="block text-[12px] text-mist-100">{item.name}</span>
                      <span className="mt-0.5 block font-mono text-[10.5px] text-mist-600">
                        {item.sku}
                      </span>
                    </TableCell>
                    <TableCell className="text-right text-[12px] whitespace-nowrap">
                      {formatQuantity(item.quantity, item.unit)}
                    </TableCell>
                    <TableCell className="text-right text-[12px] whitespace-nowrap">
                      {formatMoney(item.unit_price, deal.currency)}
                    </TableCell>
                    <TableCell className="pr-5 text-right whitespace-nowrap">
                      <span className="data-value text-[12px] text-mist-100">
                        {formatMoney(item.line_total, deal.currency)}
                      </span>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <div className="flex items-center justify-between gap-3 border-t border-white/[0.07] px-5 py-3">
              <span className="text-[10px] tracking-[0.14em] text-mist-600 uppercase">
                Total value
              </span>
              <span className="data-value text-[14px] text-mist-100">
                {formatMoney(deal.total_value, deal.currency)}
              </span>
            </div>
          </div>

          {deal.notes ? (
            <div className="panel px-5 py-4">
              <p className="eyebrow">Notes</p>
              <p className="mt-2 text-[12px] leading-relaxed whitespace-pre-line text-mist-400">
                {deal.notes}
              </p>
            </div>
          ) : null}

          <HistoryPanel deal={deal} />
        </div>

        <aside className="space-y-4 self-start xl:sticky xl:top-20">
          <div className="panel-elevated overflow-hidden">
            <div className="px-5 pt-4.5 pb-3">
              <p className="eyebrow">Next step</p>
              <h2 className="mt-1.5 text-[14px] font-medium text-mist-100">Move this deal</h2>
              <p className="mt-1 text-[11px] leading-relaxed text-mist-500">
                Only transitions allowed by the deal state machine are offered. Every change is
                versioned and audited.
              </p>
            </div>
            <div className="hairline" />
            <div className="p-5">
              <TransitionPanel deal={deal} csrfToken={session.csrf_token} canWrite={canWrite} />
            </div>
          </div>

          <div className="panel overflow-hidden">
            <div className="px-5 pt-4.5 pb-3">
              <p className="eyebrow">Header</p>
              <h2 className="mt-1.5 text-[14px] font-medium text-mist-100">Edit deal details</h2>
            </div>
            <div className="hairline" />
            <div className="p-5">
              <DealEditForm deal={deal} csrfToken={session.csrf_token} canWrite={canWrite} />
            </div>
          </div>
        </aside>
      </section>
    </div>
  );
}

function HistoryPanel({ deal }: { deal: Deal }) {
  return (
    <div className="panel overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 px-5 pt-4.5 pb-3">
        <div className="flex items-center gap-2">
          <History className="size-3.5 text-accent-300" aria-hidden />
          <div>
            <p className="eyebrow">History</p>
            <h2 className="mt-1.5 text-[14px] font-medium text-mist-100">Recorded transitions</h2>
          </div>
        </div>
        <span className="text-[10.5px] text-mist-600">
          {deal.transitions.length} {deal.transitions.length === 1 ? "entry" : "entries"}
        </span>
      </div>
      <div className="hairline" />
      <ol className="px-5 py-4">
        {deal.transitions.map((transition, index) => {
          const last = index === deal.transitions.length - 1;
          return (
            <li key={transition.id} className="relative flex gap-3 pb-4 last:pb-0">
              {last ? null : (
                <span className="absolute top-3 bottom-0 left-[3px] w-px bg-white/10" aria-hidden />
              )}
              <span
                className={cn(
                  "relative mt-1.5 size-[7px] shrink-0 rounded-full ring-2 ring-ink-900",
                  transition.to_status === "WON"
                    ? "bg-jade-400"
                    : transition.to_status === "LOST" || transition.to_status === "CANCELLED"
                      ? "bg-crimson-400"
                      : transition.to_status === "NEGOTIATION"
                        ? "bg-amber-400"
                        : "bg-accent-400",
                )}
                aria-hidden
              />
              <div className="min-w-0 flex-1">
                <p className="text-[12px] text-mist-300">
                  {transition.from_status ? `${transition.from_status} → ` : "Created · "}
                  <span className="text-mist-100">{transition.to_status}</span>
                </p>
                {transition.reason ? (
                  <p className="mt-0.5 text-[11px] leading-relaxed text-mist-500">
                    “{transition.reason}”
                  </p>
                ) : null}
                <p className="mt-0.5 font-mono text-[10px] text-mist-600">
                  v{transition.version_after} · {formatTimestamp(transition.occurred_at)}
                </p>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
