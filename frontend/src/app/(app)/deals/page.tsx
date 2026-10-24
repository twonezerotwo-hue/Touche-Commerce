import Link from "next/link";
import { ArrowRight, CalendarClock, Handshake, Plus, Search, X } from "lucide-react";

import { DealStatusBadge } from "@/components/trade/status-badge";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/ui/page-header";
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
import { getServerT } from "@/lib/i18n/server";
import { dealStatusLabel } from "@/lib/i18n/value-labels";
import { formatDate, formatMoney, formatTimestamp, withQuery } from "@/lib/trade/format";
import { DEAL_STATUSES, type DealList } from "@/lib/trade/types";
import { cn } from "@/lib/utils";

export const dynamic = "force-dynamic";
export const metadata = { title: "Deals" };

const PAGE_SIZE = 25;

export default async function DealsPage({
  searchParams,
}: {
  searchParams: Promise<{ search?: string; status?: string; cursor?: string }>;
}) {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;
  const { t } = await getServerT();

  const params = await searchParams;
  const canWrite = state.session.session.company?.permissions.includes("trade.write") ?? false;

  const query = new URLSearchParams({ limit: String(PAGE_SIZE) });
  if (params.search) query.set("search", params.search);
  if (params.status) query.set("status", params.status);
  if (params.cursor) query.set("cursor", params.cursor);

  const result = await serverGet<DealList>(`/deals?${query.toString()}`);
  const filters = { search: params.search ?? "", status: params.status ?? "" };
  const filtered = Boolean(filters.search || filters.status);
  const today = new Date().toISOString().slice(0, 10);

  return (
    <div className="mx-auto max-w-[1360px] space-y-5">
      <PageHeader
        eyebrow={t("dealsEyebrow")}
        meta={<Badge variant="secondary">{t("dealsBadge")}</Badge>}
        title={t("dealsBadge")}
        description={t("dealsDescription")}
        actions={
          canWrite ? (
            <Button asChild size="sm">
              <Link href="/deals/new">
                <Plus className="size-3.5" aria-hidden />
                {t("dashNewDeal")}
              </Link>
            </Button>
          ) : (
            <Badge variant="outline">{t("dealsReadOnlyBadge")}</Badge>
          )
        }
      />

      <div className="panel overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
          <nav aria-label={t("filterByStatus")} className="flex flex-wrap items-center gap-1.5">
            <FilterPill
              href={withQuery("/deals", { search: filters.search })}
              active={filters.status === ""}
            >
              {t("dealsFilterAll")}
            </FilterPill>
            {DEAL_STATUSES.map((status) => (
              <FilterPill
                key={status}
                href={withQuery("/deals", { search: filters.search, status })}
                active={filters.status === status}
              >
                {dealStatusLabel(t, status)}
              </FilterPill>
            ))}
          </nav>

          <form action="/deals" method="get" className="flex items-center gap-2">
            <input type="hidden" name="status" value={filters.status} />
            <div className="relative">
              <Search
                className="pointer-events-none absolute top-1/2 left-3 size-3.5 -translate-y-1/2 text-mist-600"
                aria-hidden
              />
              <Input
                id="deals-search"
                name="search"
                defaultValue={filters.search}
                placeholder={t("dealsSearchPlaceholder")}
                aria-label={t("dealsSearchLabel")}
                maxLength={160}
                className="h-8 w-[220px] pl-8 text-[12px]"
              />
            </div>
            <Button type="submit" size="sm" variant="subtle">
              {t("actionSearch")}
            </Button>
            {filters.search ? (
              <Button asChild size="iconSm" variant="ghost" aria-label={t("dealsClearSearch")}>
                <Link href={withQuery("/deals", { status: filters.status })}>
                  <X className="size-3.5" aria-hidden />
                </Link>
              </Button>
            ) : null}
          </form>
        </div>

        <div className="hairline" />

        {!result.ok ? (
          <div className="p-4">
            <Alert variant="danger" title={t("dealsUnavailable")}>
              {result.message}
              {result.requestId ? (
                <span className="ml-1 font-mono text-[11px]">({result.requestId})</span>
              ) : null}
            </Alert>
          </div>
        ) : result.data.items.length === 0 ? (
          <div className="p-4">
            <EmptyState
              icon={<Handshake className="size-4" aria-hidden />}
              title={filtered ? t("dealsNoMatch") : t("dealsNone")}
              description={
                filtered
                  ? t("dealsNoMatchHint")
                  : canWrite
                    ? t("dealsEmptyWrite")
                    : t("dashNoDealsRead")
              }
              action={
                filtered ? (
                  <Button asChild variant="outline" size="sm">
                    <Link href="/deals">{t("filterClear")}</Link>
                  </Button>
                ) : canWrite ? (
                  <Button asChild size="sm">
                    <Link href="/deals/new">{t("dashNewDeal")}</Link>
                  </Button>
                ) : null
              }
              className="border-dashed bg-transparent py-10"
            />
          </div>
        ) : (
          <Table bare>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-4">{t("columnReference")}</TableHead>
                <TableHead>{t("dealsColTitle")}</TableHead>
                <TableHead>{t("dashColCounterparty")}</TableHead>
                <TableHead>{t("columnStatus")}</TableHead>
                <TableHead>{t("dealsColExpectedClose")}</TableHead>
                <TableHead className="text-right">{t("dashColValue")}</TableHead>
                <TableHead className="pr-4 text-right">{t("dealsColCreated")}</TableHead>
                <TableHead className="w-8 pr-3">
                  <span className="sr-only">{t("opsOpen")}</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {result.data.items.map((deal) => {
                const overdue =
                  deal.expected_close_date !== null &&
                  deal.expected_close_date < today &&
                  ["DRAFT", "OPEN", "NEGOTIATION"].includes(deal.status);
                return (
                  <TableRow key={deal.id}>
                    <TableCell className="pl-4">
                      <Link
                        href={`/deals/${deal.id}`}
                        className="font-mono text-[11.5px] text-accent-200 transition-colors hover:text-accent-100"
                      >
                        {deal.reference}
                      </Link>
                    </TableCell>
                    <TableCell className="max-w-[260px] truncate text-[12px] text-mist-100">
                      {deal.title}
                    </TableCell>
                    <TableCell className="max-w-[200px] truncate text-[12px]">
                      {deal.counterparty_name}
                    </TableCell>
                    <TableCell>
                      <DealStatusBadge status={deal.status} />
                    </TableCell>
                    <TableCell className="whitespace-nowrap">
                      <span className="flex items-center gap-1.5 text-[11.5px] text-mist-400">
                        {overdue ? (
                          <CalendarClock className="size-3 text-amber-400" aria-hidden />
                        ) : null}
                        {formatDate(deal.expected_close_date)}
                      </span>
                      {overdue ? (
                        <span className="mt-0.5 block text-[9.5px] tracking-[0.08em] text-amber-400 uppercase">
                          {t("dealsPastClose")}
                        </span>
                      ) : null}
                    </TableCell>
                    <TableCell className="text-right whitespace-nowrap">
                      <span className="data-value text-[12px] text-mist-200">
                        {formatMoney(deal.total_value, deal.currency)}
                      </span>
                    </TableCell>
                    <TableCell className="pr-4 text-right font-mono text-[10.5px] whitespace-nowrap text-mist-600">
                      {formatTimestamp(deal.created_at)}
                    </TableCell>
                    <TableCell className="pr-3 text-right">
                      <Link
                        href={`/deals/${deal.id}`}
                        aria-label={t("dealsOpenRef", { reference: deal.reference })}
                        className="inline-flex text-mist-600 transition-colors hover:text-accent-300"
                      >
                        <ArrowRight className="size-3.5" aria-hidden />
                      </Link>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-white/[0.06] px-4 py-3">
          <p className="text-[10.5px] text-mist-600">
            {result.ok ? (
              <>
                {result.data.items.length === 1
                  ? t("dealsShowingOne")
                  : t("dealsShowingMany", { count: result.data.items.length })}
                {" · "}
                {result.data.has_more ? t("dealsOlder") : t("dealsEnd")}
              </>
            ) : (
              "—"
            )}
          </p>
          <div className="flex items-center gap-3">
            {params.cursor ? (
              <Button asChild variant="ghost" size="xs">
                <Link href={withQuery("/deals", filters)}>{t("pageFirst")}</Link>
              </Button>
            ) : null}
            {result.ok && result.data.has_more && result.data.next_cursor ? (
              <Button asChild variant="outline" size="sm">
                <Link href={withQuery("/deals", { ...filters, cursor: result.data.next_cursor })}>
                  {t("pageNextPage")}
                  <ArrowRight className="size-3.5" aria-hidden />
                </Link>
              </Button>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}

function FilterPill({
  href,
  active,
  children,
}: {
  href: string;
  active: boolean;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      aria-current={active ? "true" : undefined}
      className={cn(
        "rounded-full border px-2.5 py-1 text-[10.5px] tracking-[0.02em] transition-colors",
        active
          ? "border-accent-400/35 bg-accent-400/10 text-accent-200"
          : "border-white/10 text-mist-500 hover:border-white/20 hover:text-mist-300",
      )}
    >
      {children}
    </Link>
  );
}
