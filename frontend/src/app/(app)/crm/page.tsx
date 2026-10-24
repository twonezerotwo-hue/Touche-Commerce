import Link from "next/link";
import { ArrowRight, Search, Users, X } from "lucide-react";

import { CounterpartyForm } from "@/components/trade/counterparty-form";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/ui/page-header";
import { Select } from "@/components/ui/select";
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
import { counterpartyTypeLabel, recordStatusLabel } from "@/lib/i18n/value-labels";
import { formatTimestamp, withQuery } from "@/lib/trade/format";
import type { CounterpartyList } from "@/lib/trade/types";

export const dynamic = "force-dynamic";
export const metadata = { title: "CRM" };

const PAGE_SIZE = 25;

export default async function CrmPage({
  searchParams,
}: {
  searchParams: Promise<{ search?: string; status?: string; cursor?: string }>;
}) {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;
  const { t } = await getServerT();

  const params = await searchParams;
  const company = state.session.session.company;
  const canWrite = company?.permissions.includes("trade.write") ?? false;

  const query = new URLSearchParams({ limit: String(PAGE_SIZE) });
  if (params.search) query.set("search", params.search);
  if (params.status) query.set("status", params.status);
  if (params.cursor) query.set("cursor", params.cursor);

  const result = await serverGet<CounterpartyList>(`/counterparties?${query.toString()}`);
  const filters = { search: params.search ?? "", status: params.status ?? "" };
  const filtered = Boolean(filters.search || filters.status);

  return (
    <div className="mx-auto max-w-[1360px] space-y-5">
      <PageHeader
        eyebrow={t("crmEyebrow")}
        meta={<Badge variant="secondary">{t("crmBadge")}</Badge>}
        title={t("crmTitle")}
        description={t("crmDescription")}
        actions={
          <CounterpartyForm csrfToken={state.session.session.csrf_token} canWrite={canWrite} />
        }
      />

      <div className="panel overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div>
            <p className="eyebrow">{t("crmSection")}</p>
            <h2 className="mt-1.5 text-[14px] font-medium text-mist-100">{t("crmSubtitle")}</h2>
          </div>

          <form action="/crm" method="get" className="flex flex-wrap items-center gap-2">
            <div className="relative">
              <Search
                className="pointer-events-none absolute top-1/2 left-3 size-3.5 -translate-y-1/2 text-mist-600"
                aria-hidden
              />
              <Input
                id="crm-search"
                name="search"
                defaultValue={filters.search}
                placeholder={t("crmSearch")}
                aria-label={t("crmSearch")}
                maxLength={160}
                className="h-8 w-[220px] pl-8 text-[12px]"
              />
            </div>
            <div className="w-[128px]">
              <Select
                id="crm-status"
                name="status"
                defaultValue={filters.status}
                aria-label={t("filterByStatus")}
                className="h-8 text-[12px]"
              >
                <option value="">{t("filterAllStatuses")}</option>
                <option value="active">{t("statusActive")}</option>
                <option value="inactive">{t("statusInactive")}</option>
              </Select>
            </div>
            <Button type="submit" size="sm" variant="subtle">
              {t("filterButton")}
            </Button>
            {filtered ? (
              <Button asChild size="iconSm" variant="ghost" aria-label={t("filterClear")}>
                <Link href="/crm">
                  <X className="size-3.5" aria-hidden />
                </Link>
              </Button>
            ) : null}
          </form>
        </div>

        <div className="hairline" />

        {!result.ok ? (
          <div className="p-4">
            <Alert variant="danger" title={t("crmUnavailable")}>
              {result.message}
              {result.requestId ? (
                <span className="ml-1 font-mono text-[11px]">({result.requestId})</span>
              ) : null}
            </Alert>
          </div>
        ) : result.data.items.length === 0 ? (
          <div className="p-4">
            <EmptyState
              icon={<Users className="size-4" aria-hidden />}
              title={filtered ? t("crmNoMatch") : t("crmEmpty")}
              description={filtered ? t("crmNoMatchHint") : t("crmEmptyHint")}
              action={
                filtered ? (
                  <Button asChild variant="outline" size="sm">
                    <Link href="/crm">{t("filterClear")}</Link>
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
                <TableHead className="pl-4">{t("columnName")}</TableHead>
                <TableHead>{t("columnType")}</TableHead>
                <TableHead>{t("columnCountry")}</TableHead>
                <TableHead>{t("columnContact")}</TableHead>
                <TableHead>{t("columnStatus")}</TableHead>
                <TableHead className="pr-4 text-right">{t("columnUpdated")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {result.data.items.map((counterparty) => (
                <TableRow key={counterparty.id}>
                  <TableCell className="pl-4">
                    <span className="block text-[12px] text-mist-100">{counterparty.name}</span>
                    {counterparty.email ? (
                      <span className="mt-0.5 block text-[10.5px] text-mist-600">
                        {counterparty.email}
                      </span>
                    ) : null}
                  </TableCell>
                  <TableCell>
                    <Badge variant="secondary" className="capitalize">
                      {counterpartyTypeLabel(t, counterparty.type)}
                    </Badge>
                  </TableCell>
                  <TableCell className="font-mono text-[11px] text-mist-400">
                    {counterparty.country ?? "—"}
                  </TableCell>
                  <TableCell className="text-[12px]">{counterparty.contact_name ?? "—"}</TableCell>
                  <TableCell>
                    <Badge dot variant={counterparty.status === "active" ? "success" : "outline"}>
                      {recordStatusLabel(t, counterparty.status)}
                    </Badge>
                  </TableCell>
                  <TableCell className="pr-4 text-right font-mono text-[10.5px] whitespace-nowrap text-mist-600">
                    {formatTimestamp(counterparty.updated_at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-white/[0.06] px-4 py-3">
          <p className="text-[10.5px] text-mist-600">
            {result.ok ? (
              <>
                <span className="data-value text-mist-400">{result.data.items.length}</span>{" "}
                {t("listShown")}
                {" · "}
                {result.data.has_more ? t("productsOlder") : t("crmEnd")}
              </>
            ) : (
              "—"
            )}
          </p>
          <div className="flex items-center gap-3">
            {params.cursor ? (
              <Button asChild variant="ghost" size="xs">
                <Link href={withQuery("/crm", filters)}>{t("pageFirst")}</Link>
              </Button>
            ) : null}
            {result.ok && result.data.has_more && result.data.next_cursor ? (
              <Button asChild variant="outline" size="sm">
                <Link href={withQuery("/crm", { ...filters, cursor: result.data.next_cursor })}>
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
