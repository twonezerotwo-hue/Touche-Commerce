import Link from "next/link";

import { SalesQuoteActions } from "@/components/sourcing/sales-quote-actions";
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
import type { SalesQuote } from "@/lib/sourcing/types";
import { formatDate, formatMoney, formatQuantity, formatTimestamp } from "@/lib/trade/format";

export const dynamic = "force-dynamic";

export default async function SalesQuoteDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;
  const permissions = state.session.session.company?.permissions ?? [];
  const canWrite = permissions.includes("trade.write");
  const canApprove = permissions.includes("finance.approve");
  const { id } = await params;

  const result = await serverGet<SalesQuote>(`/sales-quotes/${id}`);
  if (!result.ok) {
    return (
      <div className="mx-auto max-w-[900px] space-y-4">
        <PageHeader
          eyebrow="Sales quote"
          back={{ href: "/sales-quotes", label: "Sales quotes" }}
          title="Quote unavailable"
        />
        <Alert variant="danger" title="Could not load this sales quote">
          {result.message}
        </Alert>
      </div>
    );
  }

  const quote = result.data;

  return (
    <div className="mx-auto max-w-[1200px] space-y-5">
      <PageHeader
        eyebrow="Sales quote"
        back={{ href: "/sales-quotes", label: "Sales quotes" }}
        meta={
          <div className="flex items-center gap-2">
            <SourcingStatusBadge status={quote.status} />
            <Badge variant="outline">r{quote.revision}</Badge>
            <SourcingStatusBadge status={quote.scenario_status} />
          </div>
        }
        title={`${quote.quote_number} · ${formatMoney(quote.total_value, quote.currency)}`}
        description={`${quote.customer_name} · deal ${quote.deal_reference} · ${quote.incoterm} ${quote.named_delivery_place} · valid until ${formatDate(quote.valid_until)}`}
      />

      <div className="grid gap-4 lg:grid-cols-[1.6fr_1fr]">
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>Quoted lines</CardTitle>
                <CardDescription>{quote.payment_terms}</CardDescription>
              </CardHeading>
              <Badge variant="outline">{quote.currency}</Badge>
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
                  {quote.items.map((item) => (
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
                        {formatMoney(item.unit_price, quote.currency)}
                      </TableCell>
                      <TableCell className="text-right text-[12px] text-mist-100">
                        {formatMoney(item.line_total, quote.currency)}
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
                <CardTitle>Approval trail</CardTitle>
                <CardDescription>
                  Submitting and approving are separate, audited steps.
                </CardDescription>
              </CardHeading>
            </CardHeader>
            <CardContent>
              <dl className="space-y-2 text-[11.5px]">
                <div>
                  <dt className="eyebrow">Submitted</dt>
                  <dd className="text-mist-200">
                    {formatTimestamp(quote.submitted_at)}
                    {quote.submitted_by ? (
                      <span className="ml-1 font-mono text-[10px] text-mist-500">
                        {quote.submitted_by.slice(0, 8)}…
                      </span>
                    ) : null}
                  </dd>
                </div>
                <div>
                  <dt className="eyebrow">Approved</dt>
                  <dd className="text-mist-200">
                    {formatTimestamp(quote.approved_at)}
                    {quote.approved_by ? (
                      <span className="ml-1 font-mono text-[10px] text-mist-500">
                        {quote.approved_by.slice(0, 8)}…
                      </span>
                    ) : null}
                  </dd>
                </div>
                {quote.rejection_reason ? (
                  <div>
                    <dt className="eyebrow">Rejection reason</dt>
                    <dd className="text-mist-300">{quote.rejection_reason}</dd>
                  </div>
                ) : null}
                <div>
                  <dt className="eyebrow">Supersedes</dt>
                  <dd className="font-mono text-[10.5px] text-mist-400">
                    {quote.supersedes_sales_quote_id ?? "—"}
                  </dd>
                </div>
                <div>
                  <dt className="eyebrow">Superseded by</dt>
                  <dd className="font-mono text-[10.5px] text-mist-400">
                    {quote.superseded_by_sales_quote_id ?? "—"}
                  </dd>
                </div>
                {quote.notes ? (
                  <div>
                    <dt className="eyebrow">Notes</dt>
                    <dd className="text-mist-300">{quote.notes}</dd>
                  </div>
                ) : null}
              </dl>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>Workflow</CardTitle>
                <CardDescription>
                  Submit, then approve or reject. Approved quotes are revised, never withdrawn.
                </CardDescription>
              </CardHeading>
            </CardHeader>
            <CardContent>
              <SalesQuoteActions
                quote={quote}
                csrfToken={state.session.session.csrf_token}
                canWrite={canWrite}
                canApprove={canApprove}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>Revision snapshots</CardTitle>
                <CardDescription>One immutable row per customer-facing revision.</CardDescription>
              </CardHeading>
            </CardHeader>
            <CardContent className="space-y-2">
              {quote.revisions.map((revision) => (
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
            href={`/pricing/${quote.scenario_id}`}
            className="inline-flex text-[12px] text-accent-200 hover:text-accent-100"
          >
            Open the pricing scenario behind this quote
          </Link>
        </div>
      </div>
    </div>
  );
}
