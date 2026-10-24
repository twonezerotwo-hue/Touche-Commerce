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
import { DocumentDownloads } from "@/components/documents/document-downloads";
import { canGenerateDocuments } from "@/lib/documents/access";
import { getServerT, titleFor } from "@/lib/i18n/server";
import type { SalesQuote } from "@/lib/sourcing/types";
import { formatDate, formatMoney, formatQuantity, formatTimestamp } from "@/lib/trade/format";

export const dynamic = "force-dynamic";
export const generateMetadata = () => titleFor("slqEyebrow");

export default async function SalesQuoteDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;
  const { t, locale } = await getServerT();
  const permissions = state.session.session.company?.permissions ?? [];
  const canWrite = permissions.includes("trade.write");
  const canApprove = permissions.includes("finance.approve");
  const { id } = await params;

  const result = await serverGet<SalesQuote>(`/sales-quotes/${id}`);
  if (!result.ok) {
    return (
      <div className="mx-auto max-w-[900px] space-y-4">
        <PageHeader
          eyebrow={t("slqEyebrow")}
          back={{ href: "/sales-quotes", label: t("slqBadge") }}
          title={t("slqUnavailableTitle")}
        />
        <Alert variant="danger" title={t("slqLoadFailed")}>
          {result.message}
        </Alert>
      </div>
    );
  }

  const quote = result.data;

  return (
    <div className="mx-auto max-w-[1200px] space-y-5">
      <PageHeader
        eyebrow={t("slqEyebrow")}
        back={{ href: "/sales-quotes", label: t("slqBadge") }}
        meta={
          <div className="flex items-center gap-2">
            <SourcingStatusBadge status={quote.status} />
            <Badge variant="outline">r{quote.revision}</Badge>
            <SourcingStatusBadge status={quote.scenario_status} />
          </div>
        }
        title={`${quote.quote_number} · ${formatMoney(quote.total_value, quote.currency, locale)}`}
        description={t("slqHeaderDescription", {
          customer: quote.customer_name,
          deal: quote.deal_reference,
          incoterm: quote.incoterm,
          place: quote.named_delivery_place,
          date: formatDate(quote.valid_until, locale),
        })}
      />
      {canGenerateDocuments(state.session.session.company) ? (
        <DocumentDownloads documents={[{ kind: "sales_quotation", entityId: quote.id }]} />
      ) : null}

      <div className="grid gap-4 lg:grid-cols-[1.6fr_1fr]">
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>{t("suqQuotedLines")}</CardTitle>
                <CardDescription>{quote.payment_terms}</CardDescription>
              </CardHeading>
              <Badge variant="outline">{quote.currency}</Badge>
            </CardHeader>
            <CardContent>
              <Table bare>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("columnSku")}</TableHead>
                    <TableHead>{t("srcColDescription")}</TableHead>
                    <TableHead className="text-right">{t("srcColQuantity")}</TableHead>
                    <TableHead className="text-right">{t("columnUnitPrice")}</TableHead>
                    <TableHead className="text-right">{t("srcColLineTotal")}</TableHead>
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
                        {formatQuantity(item.quantity, item.unit, locale)}
                      </TableCell>
                      <TableCell className="text-right text-[12px] text-mist-200">
                        {formatMoney(item.unit_price, quote.currency, locale)}
                      </TableCell>
                      <TableCell className="text-right text-[12px] text-mist-100">
                        {formatMoney(item.line_total, quote.currency, locale)}
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
                <CardTitle>{t("slqApprovalTrail")}</CardTitle>
                <CardDescription>{t("slqApprovalTrailHint")}</CardDescription>
              </CardHeading>
            </CardHeader>
            <CardContent>
              <dl className="space-y-2 text-[11.5px]">
                <div>
                  <dt className="eyebrow">{t("slqSubmitted")}</dt>
                  <dd className="text-mist-200">
                    {formatTimestamp(quote.submitted_at, locale)}
                    {quote.submitted_by ? (
                      <span className="ml-1 font-mono text-[10px] text-mist-500">
                        {quote.submitted_by.slice(0, 8)}…
                      </span>
                    ) : null}
                  </dd>
                </div>
                <div>
                  <dt className="eyebrow">{t("slqApproved")}</dt>
                  <dd className="text-mist-200">
                    {formatTimestamp(quote.approved_at, locale)}
                    {quote.approved_by ? (
                      <span className="ml-1 font-mono text-[10px] text-mist-500">
                        {quote.approved_by.slice(0, 8)}…
                      </span>
                    ) : null}
                  </dd>
                </div>
                {quote.rejection_reason ? (
                  <div>
                    <dt className="eyebrow">{t("slqRejectionReason")}</dt>
                    <dd className="text-mist-300">{quote.rejection_reason}</dd>
                  </div>
                ) : null}
                <div>
                  <dt className="eyebrow">{t("suqSupersedes")}</dt>
                  <dd className="font-mono text-[10.5px] text-mist-400">
                    {quote.supersedes_sales_quote_id ?? "—"}
                  </dd>
                </div>
                <div>
                  <dt className="eyebrow">{t("suqSupersededBy")}</dt>
                  <dd className="font-mono text-[10.5px] text-mist-400">
                    {quote.superseded_by_sales_quote_id ?? "—"}
                  </dd>
                </div>
                {quote.notes ? (
                  <div>
                    <dt className="eyebrow">{t("srcNotes")}</dt>
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
                <CardTitle>{t("slqWorkflow")}</CardTitle>
                <CardDescription>{t("slqWorkflowHint")}</CardDescription>
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
                <CardTitle>{t("suqRevisionSnapshots")}</CardTitle>
                <CardDescription>{t("slqRevisionSnapshotsHint")}</CardDescription>
              </CardHeading>
            </CardHeader>
            <CardContent className="space-y-2">
              {quote.revisions.map((revision) => (
                <div
                  key={revision.revision}
                  className="flex items-center justify-between rounded-lg border border-white/[0.06] px-3 py-2 text-[11.5px]"
                >
                  <span className="font-mono text-mist-300">r{revision.revision}</span>
                  <span className="text-mist-600">
                    {formatTimestamp(revision.created_at, locale)}
                  </span>
                </div>
              ))}
            </CardContent>
          </Card>

          <Link
            href={`/pricing/${quote.scenario_id}`}
            className="inline-flex text-[12px] text-accent-200 hover:text-accent-100"
          >
            {t("slqOpenScenario")}
          </Link>
        </div>
      </div>
    </div>
  );
}
