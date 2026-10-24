import Link from "next/link";

import { QuoteForm } from "@/components/sourcing/quote-form";
import { RfqActions } from "@/components/sourcing/rfq-actions";
import { SourcingStatusBadge } from "@/components/sourcing/status-badge";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
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
import { getServerT, titleFor, type ServerTranslator } from "@/lib/i18n/server";
import type { Rfq } from "@/lib/sourcing/types";
import { formatDate, formatMoney, formatQuantity, formatTimestamp } from "@/lib/trade/format";

export const dynamic = "force-dynamic";
export const generateMetadata = () => titleFor("rfqEyebrow");

export default async function RfqDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;
  const { t, locale } = await getServerT();
  const canWrite = state.session.session.company?.permissions.includes("trade.write") ?? false;
  const { id } = await params;
  const result = await serverGet<Rfq>(`/rfqs/${id}`);
  if (!result.ok) {
    return (
      <div className="mx-auto max-w-[900px] space-y-4">
        <PageHeader
          eyebrow={t("rfqEyebrow")}
          back={{ href: "/rfq", label: t("rfqPageTitle") }}
          title={t("rfqUnavailableTitle")}
        />
        <Alert variant="danger" title={t("rfqLoadFailed")}>
          {result.message}
        </Alert>
        <Link href="/rfq" className="text-[12px] text-accent-200">
          {t("rfqBackTo")}
        </Link>
      </div>
    );
  }
  return (
    <RfqDetail
      rfq={result.data}
      canWrite={canWrite}
      canGenerate={canGenerateDocuments(state.session.session.company)}
      csrfToken={state.session.session.csrf_token}
      t={t}
      locale={locale}
    />
  );
}

function RfqDetail({
  rfq,
  canWrite,
  canGenerate,
  csrfToken,
  t,
  locale,
}: {
  rfq: Rfq;
  canWrite: boolean;
  canGenerate: boolean;
  csrfToken: string;
  t: ServerTranslator["t"];
  locale: ServerTranslator["locale"];
}) {
  const canQuote = canWrite && ["SENT", "RESPONDED"].includes(rfq.status);

  return (
    <div className="mx-auto max-w-[1200px] space-y-5">
      <PageHeader
        eyebrow={t("rfqEyebrow")}
        back={{ href: "/rfq", label: t("rfqPageTitle") }}
        meta={<SourcingStatusBadge status={rfq.status} />}
        title={rfq.reference_number}
        description={t("rfqHeaderDescription", {
          supplier: rfq.supplier_name,
          deal: rfq.deal_reference,
          place: rfq.delivery_location,
        })}
      />

      {canGenerate ? <DocumentDownloads documents={[{ kind: "rfq", entityId: rfq.id }]} /> : null}

      <div className="grid gap-4 lg:grid-cols-[1.6fr_1fr]">
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>{t("rfqRequestedLines")}</CardTitle>
                <CardDescription>{t("rfqRequestedLinesHint")}</CardDescription>
              </CardHeading>
              <Badge variant="outline">{rfq.requested_currency}</Badge>
            </CardHeader>
            <CardContent>
              <Table bare>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("columnSku")}</TableHead>
                    <TableHead>{t("srcColDescription")}</TableHead>
                    <TableHead className="text-right">{t("srcColQuantity")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rfq.items.map((item) => (
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
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>{t("rfqQuotesReceived")}</CardTitle>
                <CardDescription>{t("rfqQuotesReceivedHint")}</CardDescription>
              </CardHeading>
            </CardHeader>
            <CardContent className="space-y-2">
              {rfq.quotes.length === 0 ? (
                <p className="text-[11.5px] text-mist-600">{t("rfqNoQuotes")}</p>
              ) : (
                rfq.quotes.map((quote) => (
                  <div
                    key={quote.id}
                    className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-white/[0.06] px-3 py-2"
                  >
                    <div className="flex items-center gap-2">
                      <Link
                        href={`/quotes/${quote.id}`}
                        className="font-mono text-[11.5px] text-accent-200 hover:text-accent-100"
                      >
                        {t("rfqRevisionN", { n: quote.revision })}
                      </Link>
                      <SourcingStatusBadge status={quote.status} />
                      <span className="text-[11.5px] text-mist-400">
                        {formatMoney(quote.total_value, quote.currency, locale)}
                      </span>
                    </div>
                    <span className="text-[10.5px] text-mist-600">
                      {t("rfqValidUntil", { date: formatDate(quote.valid_until, locale) })}
                    </span>
                  </div>
                ))
              )}
            </CardContent>
          </Card>

          {canQuote ? (
            <Card>
              <CardHeader>
                <CardHeading>
                  <CardTitle>{t("rfqRecordQuote")}</CardTitle>
                  <CardDescription>{t("rfqRecordQuoteHint")}</CardDescription>
                </CardHeading>
              </CardHeader>
              <CardContent>
                <QuoteForm
                  rfq={rfq}
                  csrfToken={csrfToken}
                  defaultCurrency={rfq.requested_currency}
                />
              </CardContent>
            </Card>
          ) : null}
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>{t("rfqLifecycle")}</CardTitle>
                <CardDescription>{t("rfqLifecycleHint")}</CardDescription>
              </CardHeading>
            </CardHeader>
            <CardContent>
              <RfqActions rfq={rfq} csrfToken={csrfToken} canWrite={canWrite} />
            </CardContent>
            <CardFooter>
              <dl className="grid w-full grid-cols-2 gap-2 text-[11px] text-mist-500">
                <div>
                  <dt className="eyebrow">{t("rfqPreparedRevision")}</dt>
                  <dd className="data-value text-mist-200">r{rfq.revision}</dd>
                </div>
                <div>
                  <dt className="eyebrow">{t("rfqDue")}</dt>
                  <dd className="text-mist-200">{formatDate(rfq.response_due_date, locale)}</dd>
                </div>
                <div>
                  <dt className="eyebrow">{t("rfqChannel")}</dt>
                  <dd className="text-mist-200">{rfq.sent_channel ?? "—"}</dd>
                </div>
                <div>
                  <dt className="eyebrow">{t("rfqSent")}</dt>
                  <dd className="text-mist-200">{formatTimestamp(rfq.sent_at, locale)}</dd>
                </div>
              </dl>
            </CardFooter>
          </Card>

          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>{t("rfqPreparedRevisions")}</CardTitle>
                <CardDescription>{t("rfqPreparedRevisionsHint")}</CardDescription>
              </CardHeading>
            </CardHeader>
            <CardContent className="space-y-2">
              {rfq.revisions.length === 0 ? (
                <p className="text-[11.5px] text-mist-600">{t("rfqNotPrepared")}</p>
              ) : (
                rfq.revisions.map((revision) => (
                  <div
                    key={revision.revision}
                    className="flex items-center justify-between rounded-lg border border-white/[0.06] px-3 py-2 text-[11.5px]"
                  >
                    <span className="font-mono text-mist-300">r{revision.revision}</span>
                    <span className="text-mist-600">
                      {formatTimestamp(revision.created_at, locale)}
                    </span>
                  </div>
                ))
              )}
            </CardContent>
          </Card>

          {rfq.sent_evidence ? (
            <Alert variant="info" title={t("rfqDispatchEvidence")}>
              <span className="font-mono text-[11px]">{rfq.sent_evidence}</span>
            </Alert>
          ) : null}
        </div>
      </div>
    </div>
  );
}
