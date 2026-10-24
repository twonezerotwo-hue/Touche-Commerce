import Link from "next/link";

import { SalesQuoteForm } from "@/components/sourcing/sales-quote-form";
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
import { getServerT, titleFor } from "@/lib/i18n/server";
import { costBasisText, costTypeText, verificationText } from "@/lib/i18n/value-labels";
import { formatPercent } from "@/lib/sourcing/format";
import type { PricingScenario } from "@/lib/sourcing/types";
import type { CounterpartyList } from "@/lib/trade/types";
import { formatMoney, formatQuantity, formatTimestamp } from "@/lib/trade/format";

export const dynamic = "force-dynamic";
export const generateMetadata = () => titleFor("prcEyebrow");

interface ResultLine {
  product_id: string;
  description: string;
  unit: string;
  quantity: string;
  landed_unit_cost: string;
  unit_sale_price: string;
  line_sale_price: string;
  line_margin: string;
  allocated_cost: string;
}

interface ResultTotals {
  purchase_total: string;
  additional_cost_total: string;
  landed_total: string;
  sales_total: string;
  gross_margin: string;
  gross_margin_pct: string;
}

export default async function PricingDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;
  const { t, locale } = await getServerT();
  const canWrite = state.session.session.company?.permissions.includes("trade.write") ?? false;
  const { id } = await params;

  const [scenario, buyers] = await Promise.all([
    serverGet<PricingScenario>(`/pricing-scenarios/${id}`),
    serverGet<CounterpartyList>("/counterparties?limit=100&status=active&type=buyer"),
  ]);

  if (!scenario.ok) {
    return (
      <div className="mx-auto max-w-[900px] space-y-4">
        <PageHeader
          eyebrow={t("prcEyebrow")}
          back={{ href: "/pricing", label: t("prcBadge") }}
          title={t("prcUnavailableTitle")}
        />
        <Alert variant="danger" title={t("prcLoadFailed")}>
          {scenario.message}
        </Alert>
      </div>
    );
  }

  const record = scenario.data;
  const results = record.calculated_results as {
    totals?: ResultTotals;
    lines?: ResultLine[];
  };
  const totals = results.totals;
  const currency = record.target_currency;
  const money = (value: string, code: string = currency) => formatMoney(value, code, locale);

  return (
    <div className="mx-auto max-w-[1200px] space-y-5">
      <PageHeader
        eyebrow={t("prcEyebrow")}
        back={{ href: "/pricing", label: t("prcBadge") }}
        meta={
          <div className="flex items-center gap-2">
            <SourcingStatusBadge status={record.status} />
            <Badge variant="outline">{record.calculation_version}</Badge>
          </div>
        }
        title={`${record.supplier_name} · ${currency}`}
        description={t("prcHeaderDescription", {
          rfq: record.rfq_reference,
          currency: record.quote_currency,
          revision: record.quote_revision,
          when: formatTimestamp(record.updated_at, locale),
        })}
      />

      {totals ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Stat
            label={t("prcStatLanded")}
            value={money(totals.landed_total)}
            detail={t("prcStatLandedDetail", {
              purchase: money(totals.purchase_total),
              costs: money(totals.additional_cost_total),
            })}
          />
          <Stat
            label={t("prcStatSales")}
            value={money(totals.sales_total)}
            detail={t("prcStatSalesDetail")}
            tone="jade"
          />
          <Stat
            label={t("prcStatMargin")}
            value={money(totals.gross_margin)}
            detail={t("prcStatMarginDetail", {
              pct: formatPercent(totals.gross_margin_pct, locale),
            })}
            tone="neutral"
          />
          <Stat
            label={t("prcStatFx")}
            value={String(record.pricing_inputs.fx_rate ?? "1")}
            detail={
              record.pricing_inputs.fx_snapshot_id
                ? t("prcStatFxSnapshot", {
                    id: String(record.pricing_inputs.fx_snapshot_id).slice(0, 8),
                  })
                : t("prcStatFxSame")
            }
            tone="amber"
          />
        </div>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-[1.6fr_1fr]">
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>{t("prcPricedLines")}</CardTitle>
                <CardDescription>{t("prcPricedLinesHint")}</CardDescription>
              </CardHeading>
            </CardHeader>
            <CardContent>
              <Table bare>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("srcColDescription")}</TableHead>
                    <TableHead className="text-right">{t("srcColQuantity")}</TableHead>
                    <TableHead className="text-right">{t("srcColAllocated")}</TableHead>
                    <TableHead className="text-right">{t("srcColLandedUnit")}</TableHead>
                    <TableHead className="text-right">{t("srcColSaleUnit")}</TableHead>
                    <TableHead className="text-right">{t("srcColLineMargin")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(results.lines ?? []).map((line) => (
                    <TableRow key={line.product_id}>
                      <TableCell className="max-w-[260px] truncate text-[12px] text-mist-100">
                        {line.description}
                      </TableCell>
                      <TableCell className="text-right text-[11.5px] text-mist-300">
                        {formatQuantity(line.quantity, line.unit, locale)}
                      </TableCell>
                      <TableCell className="text-right text-[11.5px] text-mist-300">
                        {money(line.allocated_cost)}
                      </TableCell>
                      <TableCell className="text-right text-[11.5px] text-mist-200">
                        {money(line.landed_unit_cost)}
                      </TableCell>
                      <TableCell className="text-right text-[11.5px] text-mist-100">
                        {money(line.unit_sale_price)}
                      </TableCell>
                      <TableCell className="text-right text-[11.5px] text-mist-300">
                        {money(line.line_margin)}
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
                <CardTitle>{t("prcCostComponents")}</CardTitle>
                <CardDescription>{t("prcCostComponentsHint")}</CardDescription>
              </CardHeading>
            </CardHeader>
            <CardContent>
              <Table bare>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("srcColType")}</TableHead>
                    <TableHead>{t("srcColSource")}</TableHead>
                    <TableHead>{t("srcColBasis")}</TableHead>
                    <TableHead>{t("srcColVerification")}</TableHead>
                    <TableHead className="text-right">{t("srcColAmount")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {record.components.map((component) => (
                    <TableRow key={component.id}>
                      <TableCell className="text-[11.5px] text-mist-100">
                        {costTypeText(t, component.cost_type)}
                        {component.product_sku ? (
                          <span className="ml-1 font-mono text-[10px] text-mist-500">
                            {component.product_sku}
                          </span>
                        ) : null}
                      </TableCell>
                      <TableCell className="max-w-[220px] truncate text-[11px] text-mist-400">
                        {component.source_reference}
                      </TableCell>
                      <TableCell className="text-[11px] text-mist-400">
                        {costBasisText(t, component.basis)}
                      </TableCell>
                      <TableCell className="text-[11px]">
                        <Badge
                          variant={
                            component.verification_status === "VERIFIED" ? "success" : "warning"
                          }
                        >
                          {verificationText(t, component.verification_status)}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right whitespace-nowrap text-[11.5px] text-mist-200">
                        {money(component.amount, component.currency)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>{t("prcDraftSalesQuote")}</CardTitle>
                <CardDescription>{t("prcDraftSalesQuoteHint")}</CardDescription>
              </CardHeading>
            </CardHeader>
            <CardContent>
              {canWrite ? (
                <SalesQuoteForm
                  scenario={record}
                  buyers={buyers.ok ? buyers.data.items : []}
                  csrfToken={state.session.session.csrf_token}
                />
              ) : (
                <Alert variant="info" title={t("readOnlyAccess")}>
                  {t("prcDraftNeedsWrite")}
                </Alert>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>{t("prcCompleteness")}</CardTitle>
                <CardDescription>{t("prcCompletenessHint")}</CardDescription>
              </CardHeading>
            </CardHeader>
            <CardContent>
              <dl className="space-y-2 text-[11.5px]">
                <div>
                  <dt className="eyebrow">{t("prcLinesComponents")}</dt>
                  <dd className="text-mist-200">
                    {t("prcLinesCosts", {
                      lines: String(record.completeness.line_count ?? "—"),
                      costs: String(record.completeness.component_count ?? "—"),
                    })}
                  </dd>
                </div>
                <div>
                  <dt className="eyebrow">{t("prcEstimatedComponents")}</dt>
                  <dd className="text-mist-200">
                    {String(record.completeness.estimated_component_count ?? "—")}
                  </dd>
                </div>
                <div>
                  <dt className="eyebrow">{t("prcRealised")}</dt>
                  <dd className="text-mist-200">
                    {formatPercent(String(record.completeness.realised_margin_pct ?? ""), locale)} /{" "}
                    {formatPercent(String(record.completeness.realised_markup_pct ?? ""), locale)}
                  </dd>
                </div>
              </dl>
            </CardContent>
          </Card>

          <Link
            href={`/quotes/${record.supplier_quote_id}`}
            className="inline-flex text-[12px] text-accent-200 hover:text-accent-100"
          >
            {t("prcOpenQuote")}
          </Link>
        </div>
      </div>
    </div>
  );
}
