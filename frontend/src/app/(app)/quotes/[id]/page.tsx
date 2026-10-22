import Link from "next/link";

import { PricingForm } from "@/components/sourcing/pricing-form";
import { SourcingStatusBadge } from "@/components/sourcing/status-badge";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardHeading,
  CardTitle,
} from "@/components/ui/card";
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
import type { FxRateList, SupplierQuote } from "@/lib/sourcing/types";
import { formatDate, formatMoney, formatQuantity, formatTimestamp } from "@/lib/trade/format";

export const dynamic = "force-dynamic";

export default async function SupplierQuoteDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;
  const canWrite = state.session.session.company?.permissions.includes("trade.write") ?? false;
  const { id } = await params;

  const [quote, fxRates] = await Promise.all([
    serverGet<SupplierQuote>(`/supplier-quotes/${id}`),
    serverGet<FxRateList>("/fx-rates?limit=100"),
  ]);

  if (!quote.ok) {
    return (
      <div className="mx-auto max-w-[900px] space-y-4">
        <PageHeader
          eyebrow="Supplier quote"
          back={{ href: "/quotes", label: "Supplier quotes" }}
          title="Quote unavailable"
        />
        <Alert variant="danger" title="Could not load this quote">
          {quote.message}
        </Alert>
      </div>
    );
  }

  const record = quote.data;

  return (
    <div className="mx-auto max-w-[1200px] space-y-5">
      <PageHeader
        eyebrow="Supplier quote"
        back={{ href: "/quotes", label: "Supplier quotes" }}
        meta={
          <div className="flex items-center gap-2">
            <SourcingStatusBadge status={record.status} />
            <Badge variant="outline">r{record.revision}</Badge>
            {record.superseded_by_quote_id ? <Badge variant="outline">superseded</Badge> : null}
          </div>
        }
        title={`${record.supplier_name} · ${formatMoney(record.total_value, record.currency)}`}
        description={`RFQ ${record.rfq_reference} · deal ${record.deal_reference} · ${record.incoterm} ${record.named_delivery_place} · valid until ${formatDate(record.valid_until)}`}
      />

      <div className="grid gap-4 lg:grid-cols-[1.6fr_1fr]">
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>Quoted lines</CardTitle>
                <CardDescription>
                  {record.lead_time_days} days lead time · {record.payment_terms}
                </CardDescription>
              </CardHeading>
              <Badge variant="outline">{record.currency}</Badge>
            </CardHeader>
            <CardContent>
              <Table bare>
                <TableHeader>
                  <TableRow>
                    <TableHead>SKU</TableHead>
                    <TableHead>Description</TableHead>
                    <TableHead className="text-right">Quantity</TableHead>
                    <TableHead className="text-right">Unit price</TableHead>
                    <TableHead className="text-right">Line total</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {record.items.map((item) => (
                    <TableRow key={item.id}>
                      <TableCell className="font-mono text-[11px] text-mist-400">
                        {item.sku}
                      </TableCell>
                      <TableCell className="text-[12px] text-mist-100">
                        {item.description}
                      </TableCell>
                      <TableCell className="text-right text-[12px] text-mist-200">
                        {formatQuantity(item.quantity, item.unit)}
                      </TableCell>
                      <TableCell className="text-right text-[12px] text-mist-200">
                        {formatMoney(item.unit_price, record.currency)}
                      </TableCell>
                      <TableCell className="text-right text-[12px] text-mist-100">
                        {formatMoney(item.line_total, record.currency)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>Price this quote</CardTitle>
                <CardDescription>
                  Landed cost plus selling price. FX comes from recorded snapshots only.
                </CardDescription>
              </CardHeading>
            </CardHeader>
            <CardContent>
              {record.is_active && canWrite ? (
                <PricingForm
                  quote={record}
                  fxRates={fxRates.ok ? fxRates.data.items : []}
                  csrfToken={state.session.session.csrf_token}
                />
              ) : (
                <Alert variant="info" title="This quote cannot be priced">
                  {record.is_active
                    ? "Pricing requires trade.write."
                    : "Only a received, not superseded quote can be priced. Record a revision or a new quote first."}
                </Alert>
              )}
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>Provenance</CardTitle>
                <CardDescription>Where the numbers came from.</CardDescription>
              </CardHeading>
            </CardHeader>
            <CardContent>
              <dl className="space-y-2 text-[11.5px]">
                <div>
                  <dt className="eyebrow">Source reference</dt>
                  <dd className="text-mist-200">{record.source_reference}</dd>
                </div>
                <div>
                  <dt className="eyebrow">Supplier reference</dt>
                  <dd className="text-mist-200">{record.supplier_reference ?? "—"}</dd>
                </div>
                <div>
                  <dt className="eyebrow">Received</dt>
                  <dd className="text-mist-200">{formatTimestamp(record.received_at)}</dd>
                </div>
                <div>
                  <dt className="eyebrow">Supersedes</dt>
                  <dd className="font-mono text-[10.5px] text-mist-400">
                    {record.supersedes_quote_id ?? "—"}
                  </dd>
                </div>
                <div>
                  <dt className="eyebrow">Superseded by</dt>
                  <dd className="font-mono text-[10.5px] text-mist-400">
                    {record.superseded_by_quote_id ?? "—"}
                  </dd>
                </div>
                {record.notes ? (
                  <div>
                    <dt className="eyebrow">Notes</dt>
                    <dd className="text-mist-300">{record.notes}</dd>
                  </div>
                ) : null}
              </dl>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>Revision snapshots</CardTitle>
                <CardDescription>Stored exactly as recorded.</CardDescription>
              </CardHeading>
            </CardHeader>
            <CardContent className="space-y-2">
              {record.revisions.map((revision) => (
                <div
                  key={revision.revision}
                  className="flex items-center justify-between rounded-lg border border-white/[0.06] px-3 py-2 text-[11.5px]"
                >
                  <span className="font-mono text-mist-300">r{revision.revision}</span>
                  <span className="text-mist-600">{formatTimestamp(revision.created_at)}</span>
                </div>
              ))}
            </CardContent>
          </Card>

          <Link
            href={`/rfq/${record.rfq_id}`}
            className="inline-flex text-[12px] text-accent-200 hover:text-accent-100"
          >
            Open the RFQ this quote answers
          </Link>
        </div>
      </div>
    </div>
  );
}
