import Link from "next/link";
import { ArrowRight, Package, Search, X } from "lucide-react";

import { ProductForm } from "@/components/trade/product-form";
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
import { formatMoney, formatTimestamp, withQuery } from "@/lib/trade/format";
import type { ProductList } from "@/lib/trade/types";

export const dynamic = "force-dynamic";
export const metadata = { title: "Products" };

const PAGE_SIZE = 25;

export default async function ProductsPage({
  searchParams,
}: {
  searchParams: Promise<{ search?: string; status?: string; cursor?: string }>;
}) {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;

  const params = await searchParams;
  const canWrite = state.session.session.company?.permissions.includes("trade.write") ?? false;

  const query = new URLSearchParams({ limit: String(PAGE_SIZE) });
  if (params.search) query.set("search", params.search);
  if (params.status) query.set("status", params.status);
  if (params.cursor) query.set("cursor", params.cursor);

  const result = await serverGet<ProductList>(`/products?${query.toString()}`);
  const filters = { search: params.search ?? "", status: params.status ?? "" };
  const filtered = Boolean(filters.search || filters.status);

  return (
    <div className="mx-auto max-w-[1360px] space-y-5">
      <PageHeader
        eyebrow="Catalogue"
        meta={<Badge variant="secondary">Products</Badge>}
        title="Product catalogue"
        description="SKU, unit of measure, currency and indicative price. Deal lines snapshot the agreed price, so editing a product never rewrites commercial history."
        actions={<ProductForm csrfToken={state.session.session.csrf_token} canWrite={canWrite} />}
      />

      <div className="panel overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div>
            <p className="eyebrow">Inventory</p>
            <h2 className="mt-1.5 text-[14px] font-medium text-mist-100">Tradable SKUs</h2>
          </div>

          <form action="/products" method="get" className="flex flex-wrap items-center gap-2">
            <div className="relative">
              <Search
                className="pointer-events-none absolute top-1/2 left-3 size-3.5 -translate-y-1/2 text-mist-600"
                aria-hidden
              />
              <Input
                id="products-search"
                name="search"
                defaultValue={filters.search}
                placeholder="SKU or product name"
                aria-label="Search SKU or product name"
                maxLength={160}
                className="h-8 w-[220px] pl-8 text-[12px]"
              />
            </div>
            <div className="w-[128px]">
              <Select
                id="products-status"
                name="status"
                defaultValue={filters.status}
                aria-label="Filter by status"
                className="h-8 text-[12px]"
              >
                <option value="">All statuses</option>
                <option value="active">Active</option>
                <option value="archived">Archived</option>
              </Select>
            </div>
            <Button type="submit" size="sm" variant="subtle">
              Filter
            </Button>
            {filtered ? (
              <Button asChild size="iconSm" variant="ghost" aria-label="Clear filters">
                <Link href="/products">
                  <X className="size-3.5" aria-hidden />
                </Link>
              </Button>
            ) : null}
          </form>
        </div>

        <div className="hairline" />

        {!result.ok ? (
          <div className="p-4">
            <Alert variant="danger" title="Catalogue unavailable">
              {result.message}
              {result.requestId ? (
                <span className="ml-1 font-mono text-[11px]">({result.requestId})</span>
              ) : null}
            </Alert>
          </div>
        ) : result.data.items.length === 0 ? (
          <div className="p-4">
            <EmptyState
              icon={<Package className="size-4" aria-hidden />}
              title={filtered ? "No products match" : "The catalogue is empty"}
              description={
                filtered
                  ? "Adjust the search term or status filter, or clear both to list every SKU."
                  : "Add a product before creating a deal: every deal line references a catalogue SKU."
              }
              action={
                filtered ? (
                  <Button asChild variant="outline" size="sm">
                    <Link href="/products">Clear filters</Link>
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
                <TableHead className="pl-4">SKU</TableHead>
                <TableHead>Product</TableHead>
                <TableHead>Unit</TableHead>
                <TableHead className="text-right">Unit price</TableHead>
                <TableHead>Currency</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="pr-4 text-right">Updated</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {result.data.items.map((product) => (
                <TableRow key={product.id}>
                  <TableCell className="pl-4">
                    <span className="font-mono text-[11px] tracking-[0.02em] text-accent-200">
                      {product.sku}
                    </span>
                  </TableCell>
                  <TableCell className="max-w-[280px] truncate text-[12px] text-mist-100">
                    {product.name}
                  </TableCell>
                  <TableCell className="font-mono text-[11px] text-mist-400">
                    {product.unit}
                  </TableCell>
                  <TableCell className="text-right whitespace-nowrap">
                    <span className="data-value text-[12px] text-mist-200">
                      {formatMoney(product.unit_price, product.currency)}
                    </span>
                  </TableCell>
                  <TableCell className="font-mono text-[10.5px] text-mist-600">
                    {product.currency}
                  </TableCell>
                  <TableCell>
                    <Badge dot variant={product.status === "active" ? "success" : "outline"}>
                      {product.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="pr-4 text-right font-mono text-[10.5px] whitespace-nowrap text-mist-600">
                    {formatTimestamp(product.updated_at)}
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
                <span className="data-value text-mist-400">{result.data.items.length}</span> shown
                {result.data.has_more ? " · older records available" : " · end of catalogue"}
              </>
            ) : (
              "—"
            )}
          </p>
          <div className="flex items-center gap-3">
            {params.cursor ? (
              <Button asChild variant="ghost" size="xs">
                <Link href={withQuery("/products", filters)}>First page</Link>
              </Button>
            ) : null}
            {result.ok && result.data.has_more && result.data.next_cursor ? (
              <Button asChild variant="outline" size="sm">
                <Link
                  href={withQuery("/products", { ...filters, cursor: result.data.next_cursor })}
                >
                  Next page
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
