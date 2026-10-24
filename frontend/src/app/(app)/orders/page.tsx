import Link from "next/link";

import { OperationsStatusBadge } from "@/components/operations/status-badge";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
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
import { fulfilmentModelText, operationsStatusText } from "@/lib/i18n/value-labels";
import { SALES_ORDER_STATUSES, type SalesOrderList } from "@/lib/operations/types";
import { formatMoney, formatTimestamp, withQuery } from "@/lib/trade/format";

export const dynamic = "force-dynamic";
export const metadata = { title: "Sales orders" };

const PAGE_SIZE = 25;

export default async function OrdersPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string; cursor?: string }>;
}) {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;
  const { t } = await getServerT();

  const params = await searchParams;
  const query = new URLSearchParams({ limit: String(PAGE_SIZE) });
  if (params.status) query.set("status", params.status);
  if (params.cursor) query.set("cursor", params.cursor);

  const result = await serverGet<SalesOrderList>(`/sales-orders?${query.toString()}`);
  const filters = { status: params.status ?? "" };

  return (
    <div className="mx-auto max-w-[1360px] space-y-5">
      <PageHeader
        eyebrow={t("opsEyebrow")}
        meta={
          <Badge variant="secondary">
            {result.ok
              ? t("ordOnPage", { count: result.data.items.length })
              : t("ordUnavailableBadge")}
          </Badge>
        }
        title={t("ordTitle")}
        description={t("ordDescription")}
      />

      <div className="panel overflow-hidden">
        <form action="/orders" method="get" className="flex flex-wrap items-end gap-2 px-4 py-3">
          <div className="space-y-1">
            <label htmlFor="orders-status" className="eyebrow">
              {t("columnStatus")}
            </label>
            <Select
              id="orders-status"
              name="status"
              defaultValue={filters.status}
              className="h-8 w-[190px] text-[12px]"
            >
              <option value="">{t("filterAllStatuses")}</option>
              {SALES_ORDER_STATUSES.map((status) => (
                <option key={status} value={status}>
                  {operationsStatusText(t, status)}
                </option>
              ))}
            </Select>
          </div>
          <Button type="submit" size="sm" variant="subtle">
            {t("actionApply")}
          </Button>
          {filters.status ? (
            <Button asChild size="sm" variant="ghost">
              <Link href="/orders">{t("actionClear")}</Link>
            </Button>
          ) : null}
        </form>

        <div className="hairline" />

        {!result.ok ? (
          <div className="p-4">
            <Alert variant="danger" title={t("ordUnavailable")}>
              {result.message}
            </Alert>
          </div>
        ) : result.data.items.length === 0 ? (
          <div className="p-4">
            <EmptyState title={t("ordNone")} description={t("ordNoneHint")} />
          </div>
        ) : null}

        {result.ok && result.data.items.length > 0 ? (
          <Table bare>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-4">{t("ordColOrder")}</TableHead>
                <TableHead>{t("ordColCustomer")}</TableHead>
                <TableHead>{t("ordColSource")}</TableHead>
                <TableHead>{t("ordColModel")}</TableHead>
                <TableHead>{t("columnStatus")}</TableHead>
                <TableHead className="text-right">{t("ordColTotal")}</TableHead>
                <TableHead>{t("ordColDelivery")}</TableHead>
                <TableHead className="pr-4 text-right">{t("columnUpdated")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {result.data.items.map((order) => (
                <TableRow key={order.id}>
                  <TableCell className="pl-4">
                    <Link
                      href={`/orders/${order.id}`}
                      className="font-mono text-[11.5px] text-accent-200 transition-colors hover:text-accent-100"
                    >
                      {order.order_number}
                    </Link>
                  </TableCell>
                  <TableCell className="max-w-[190px] truncate text-[12px] text-mist-100">
                    {order.customer_name}
                  </TableCell>
                  <TableCell className="text-[11px] text-mist-400">
                    <span className="font-mono">
                      {order.quote_number} r{order.sales_quote_revision}
                    </span>
                    <span className="block text-[10px] text-mist-600">{order.deal_reference}</span>
                  </TableCell>
                  <TableCell className="text-[10.5px] tracking-[0.04em] text-mist-500 uppercase">
                    {fulfilmentModelText(t, order.fulfilment_model)}
                  </TableCell>
                  <TableCell>
                    <OperationsStatusBadge status={order.status} />
                  </TableCell>
                  <TableCell className="text-right whitespace-nowrap text-[12px] text-mist-200">
                    {formatMoney(order.order_total, order.currency)}
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-[11px] text-mist-400">
                    {order.expected_delivery_date ?? "—"}
                  </TableCell>
                  <TableCell className="pr-4 text-right font-mono text-[10.5px] whitespace-nowrap text-mist-600">
                    {formatTimestamp(order.updated_at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : null}

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-white/[0.06] px-4 py-3">
          <p className="text-[10.5px] text-mist-600">{t("ordFooter")}</p>
          <div className="flex items-center gap-3">
            {params.cursor ? (
              <Button asChild variant="ghost" size="xs">
                <Link href={withQuery("/orders", filters)}>{t("pageFirst")}</Link>
              </Button>
            ) : null}
            {result.ok && result.data.has_more && result.data.next_cursor ? (
              <Button asChild variant="outline" size="sm">
                <Link
                  href={withQuery("/orders", {
                    ...filters,
                    cursor: result.data.next_cursor,
                  })}
                >
                  {t("pageNextPage")}
                </Link>
              </Button>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}
