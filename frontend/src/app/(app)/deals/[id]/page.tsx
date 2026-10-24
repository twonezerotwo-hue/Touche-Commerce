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
import { getServerT, type ServerTranslator } from "@/lib/i18n/server";
import { dealStatusLabel } from "@/lib/i18n/value-labels";
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
  const { t } = await getServerT();

  const { id } = await params;
  const result = await serverGet<Deal>(`/deals/${id}`);
  if (!result.ok) {
    if (result.code === "NOT_FOUND") notFound();
    return (
      <div className="mx-auto max-w-[1100px] space-y-4">
        <PageHeader
          eyebrow={t("dealEyebrow")}
          back={{ href: "/deals", label: t("dealsBadge") }}
          title={t("dealUnavailable")}
          description={t("dealUnavailableBody")}
        />
        <Alert variant="danger" title={t("dealUnavailable")}>
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
        back={{ href: "/deals", label: t("dealsBadge") }}
        meta={
          <>
            <DealStatusBadge status={deal.status} />
            <Badge variant="outline" className="font-mono">
              v{deal.version}
            </Badge>
            {canWrite ? null : (
              <span className="text-[10px] tracking-[0.08em] text-mist-600 uppercase">
                {t("dealReadOnly")}
              </span>
            )}
          </>
        }
        title={deal.title}
        description={
          <>
            {deal.counterparty_name} ·{" "}
            {t("dealExpectedCloseInline", { date: formatDate(deal.expected_close_date) })} ·{" "}
            <span className="data-value">{formatMoney(deal.total_value, deal.currency)}</span>
          </>
        }
        actions={
          <Button asChild variant="outline" size="sm">
            <Link href="/deals">
              <ArrowLeft className="size-3.5" aria-hidden />
              {t("dashAllDeals")}
            </Link>
          </Button>
        }
      />

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat
          label={t("dealStatValue")}
          value={formatMoney(deal.total_value, deal.currency)}
          detail={
            deal.items.length === 1
              ? t("dealComputedOne")
              : t("dealComputedMany", { count: deal.items.length })
          }
          icon={<ReceiptText className="size-3.5" aria-hidden />}
        />
        <Stat
          label={t("dealStatLines")}
          value={deal.items.length}
          detail={t("dealPricedIn", { currency: deal.currency })}
          tone="neutral"
        />
        <Stat
          label={t("dealStatVersion")}
          value={deal.version}
          detail={t("dealVersionDetail")}
          tone="neutral"
        />
        <Stat
          label={t("dealsColCreated")}
          value={formatDate(deal.created_at)}
          detail={formatTimestamp(deal.created_at)}
          tone="neutral"
        />
      </section>

      <section className="panel space-y-3 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <p className="eyebrow">{t("opsEyebrow")}</p>
            <h2 className="mt-1 text-[14px] font-medium text-mist-100">
              {deal.status === "WON" ? t("dealWonTitle") : t("dealConvertTitle")}
            </h2>
          </div>
          <Badge variant={deal.status === "WON" ? "success" : "outline"}>
            {deal.status === "WON" ? t("dealStatusWon") : t("dealNeedsAcceptance")}
          </Badge>
        </div>

        {deal.status === "WON" ? (
          <p className="text-[11.5px] text-mist-400">
            {t("dealWonBefore")}{" "}
            <Link href="/orders" className="text-accent-200 hover:text-accent-100">
              {t("dealWonLink")}
            </Link>{" "}
            {t("dealWonAfter")}
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
          <Alert variant="info" title={t("dealNotConvertible")}>
            {t("dealNotConvertibleBody")}
          </Alert>
        )}
      </section>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)]">
        <div className="space-y-4">
          <div className="panel overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-3 px-5 pt-4.5 pb-3">
              <div>
                <p className="eyebrow">{t("dealLinesEyebrow")}</p>
                <h2 className="mt-1.5 text-[14px] font-medium text-mist-100">
                  {t("dealLinesTitle")}
                </h2>
              </div>
              <span className="text-[10.5px] text-mist-500">
                {deal.items.length === 1
                  ? t("dealLineCountOne", { currency: deal.currency })
                  : t("dealLineCountMany", { count: deal.items.length, currency: deal.currency })}
              </span>
            </div>
            <div className="hairline" />
            <Table bare>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-5">{t("columnProduct")}</TableHead>
                  <TableHead className="text-right">{t("dfQuantity")}</TableHead>
                  <TableHead className="text-right">{t("columnUnitPrice")}</TableHead>
                  <TableHead className="pr-5 text-right">{t("dealColLineTotal")}</TableHead>
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
                {t("dealTotalValue")}
              </span>
              <span className="data-value text-[14px] text-mist-100">
                {formatMoney(deal.total_value, deal.currency)}
              </span>
            </div>
          </div>

          {deal.notes ? (
            <div className="panel px-5 py-4">
              <p className="eyebrow">{t("fieldNotes")}</p>
              <p className="mt-2 text-[12px] leading-relaxed whitespace-pre-line text-mist-400">
                {deal.notes}
              </p>
            </div>
          ) : null}

          <HistoryPanel deal={deal} t={t} />
        </div>

        <aside className="space-y-4 self-start xl:sticky xl:top-20">
          <div className="panel-elevated overflow-hidden">
            <div className="px-5 pt-4.5 pb-3">
              <p className="eyebrow">{t("dealNextEyebrow")}</p>
              <h2 className="mt-1.5 text-[14px] font-medium text-mist-100">{t("dealMoveTitle")}</h2>
              <p className="mt-1 text-[11px] leading-relaxed text-mist-500">{t("dealMoveHint")}</p>
            </div>
            <div className="hairline" />
            <div className="p-5">
              <TransitionPanel deal={deal} csrfToken={session.csrf_token} canWrite={canWrite} />
            </div>
          </div>

          <div className="panel overflow-hidden">
            <div className="px-5 pt-4.5 pb-3">
              <p className="eyebrow">{t("dealHeaderEyebrow")}</p>
              <h2 className="mt-1.5 text-[14px] font-medium text-mist-100">{t("dealEditTitle")}</h2>
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

function HistoryPanel({ deal, t }: { deal: Deal; t: ServerTranslator["t"] }) {
  return (
    <div className="panel overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 px-5 pt-4.5 pb-3">
        <div className="flex items-center gap-2">
          <History className="size-3.5 text-accent-300" aria-hidden />
          <div>
            <p className="eyebrow">{t("dealHistoryEyebrow")}</p>
            <h2 className="mt-1.5 text-[14px] font-medium text-mist-100">
              {t("dealHistoryTitle")}
            </h2>
          </div>
        </div>
        <span className="text-[10.5px] text-mist-600">
          {deal.transitions.length === 1
            ? t("dealEntryOne")
            : t("dealEntryMany", { count: deal.transitions.length })}
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
                  {transition.from_status
                    ? `${dealStatusLabel(t, transition.from_status)} → `
                    : t("dealCreatedDot")}
                  <span className="text-mist-100">{dealStatusLabel(t, transition.to_status)}</span>
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
