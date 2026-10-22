import Link from "next/link";
import { Search } from "lucide-react";

import { ProductForm } from "@/components/trade/product-form";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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

  return (
    <div className="mx-auto max-w-[1320px] space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <span className="eyebrow">Products</span>
            <Badge variant="secondary">Catalogue</Badge>
          </div>
          <h1 className="mt-3 font-display text-[28px] leading-tight tracking-tight text-mist-100">
            Product catalogue
          </h1>
          <p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-mist-500">
            SKU, unit of measure, currency and indicative unit price. Deal lines snapshot the agreed
            price; editing a product never rewrites history.
          </p>
        </div>
        <ProductForm csrfToken={state.session.session.csrf_token} canWrite={canWrite} />
      </header>

      <form
        action="/products"
        method="get"
        className="panel flex flex-wrap items-end gap-3 rounded-xl p-4"
      >
        <div className="min-w-[220px] flex-1 space-y-1.5">
          <label
            htmlFor="products-search"
            className="block text-[10.5px] uppercase tracking-[0.16em] text-mist-500"
          >
            Search SKU or name
          </label>
          <Input
            id="products-search"
            name="search"
            defaultValue={filters.search}
            placeholder="ALU"
            maxLength={160}
          />
        </div>
        <div className="space-y-1.5">
          <label
            htmlFor="products-status"
            className="block text-[10.5px] uppercase tracking-[0.16em] text-mist-500"
          >
            Status
          </label>
          <Select id="products-status" name="status" defaultValue={filters.status}>
            <option value="">All</option>
            <option value="active">Active</option>
            <option value="archived">Archived</option>
          </Select>
        </div>
        <Button type="submit" size="sm" variant="outline">
          <Search className="size-3.5" aria-hidden />
          Filter
        </Button>
        {filters.search || filters.status ? (
          <Link
            href="/products"
            className="text-[11.5px] text-mist-500 underline-offset-4 hover:text-mist-300 hover:underline"
          >
            Clear filters
          </Link>
        ) : null}
      </form>

      {!result.ok ? (
        <Alert variant="danger" title="Catalogue unavailable">
          {result.message}
        </Alert>
      ) : result.data.items.length === 0 ? (
        <div className="panel rounded-xl p-10 text-center">
          <p className="font-display text-lg text-mist-200">The catalogue is empty</p>
          <p className="mx-auto mt-2 max-w-md text-[12.5px] leading-relaxed text-mist-500">
            Add a product before creating a deal: every deal line references a catalogue SKU.
          </p>
        </div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>SKU</TableHead>
              <TableHead>Product</TableHead>
              <TableHead>Unit</TableHead>
              <TableHead className="text-right">Unit price</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Updated</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {result.data.items.map((product) => (
              <TableRow key={product.id}>
                <TableCell>
                  <span className="font-mono text-[12px] text-gold-200">{product.sku}</span>
                </TableCell>
                <TableCell className="text-mist-100">{product.name}</TableCell>
                <TableCell>{product.unit}</TableCell>
                <TableCell className="text-right text-mist-200">
                  {formatMoney(product.unit_price, product.currency)}
                </TableCell>
                <TableCell>
                  <Badge variant={product.status === "active" ? "success" : "outline"}>
                    {product.status}
                  </Badge>
                </TableCell>
                <TableCell className="text-right text-[11.5px] text-mist-500">
                  {formatTimestamp(product.updated_at)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      <div className="flex items-center justify-between gap-3">
        <p className="text-[11px] text-mist-600">
          {result.ok ? `${result.data.items.length} shown` : "—"}
          {result.ok && result.data.has_more ? " · more available" : ""}
        </p>
        <div className="flex items-center gap-3">
          {params.cursor ? (
            <Link
              href={withQuery("/products", filters)}
              className="text-[11.5px] text-mist-500 hover:text-mist-300"
            >
              First page
            </Link>
          ) : null}
          {result.ok && result.data.has_more && result.data.next_cursor ? (
            <Button asChild variant="outline" size="sm">
              <Link href={withQuery("/products", { ...filters, cursor: result.data.next_cursor })}>
                Next page
              </Link>
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
