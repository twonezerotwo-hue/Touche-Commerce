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
import { formatPercent } from "@/lib/sourcing/format";
import type { PricingScenario } from "@/lib/sourcing/types";
import type { CounterpartyList } from "@/lib/trade/types";
import { formatMoney, formatQuantity, formatTimestamp } from "@/lib/trade/format";

export const dynamic = "force-dynamic";

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
          eyebrow="Pricing scenario"
          back={{ href: "/pricing", label: "Pricing" }}
          title="Scenario unavailable"
        />
        <Alert variant="danger" title="Could not load this scenario">
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

  return (
    <div className="mx-auto max-w-[1200px] space-y-5">
      <PageHeader
        eyebrow="Pricing scenario"
        back={{ href: "/pricing", label: "Pricing" }}
        meta={
          <div className="flex items-center gap-2">
            <SourcingStatusBadge status={record.status} />
            <Badge variant="outline">{record.calculation_version}</Badge>
          </div>
        }
        title={`${record.supplier_name} · ${currency}`}
        description={`RFQ ${record.rfq_reference} · quote ${record.quote_currency} r${record.quote_revision} · updated ${formatTimestamp(record.updated_at)}`}
      />

      {totals ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Stat
            label="Landed cost"
            value={formatMoney(totals.landed_total, currency)}
            detail={`Purchase ${formatMoney(totals.purchase_total, currency)} + costs ${formatMoney(totals.additional_cost_total, currency)}`}
          />
          <Stat
            label="Sales value"
            value={formatMoney(totals.sales_total, currency)}
            detail="Sum of the rounded line prices"
            tone="jade"
          />
          <Stat
            label="Gross margin"
            value={formatMoney(totals.gross_margin, currency)}
            detail={`${formatPercent(totals.gross_margin_pct)} of sales`}
            tone="neutral"
          />
          <Stat
            label="FX applied"
            value={String(record.pricing_inputs.fx_rate ?? "1")}
            detail={
              record.pricing_inputs.fx_snapshot_id
                ? `snapshot ${String(record.pricing_inputs.fx_snapshot_id).slice(0, 8)}…`
                : "Same currency — no conversion"
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
                <CardTitle>Priced lines</CardTitle>
                <CardDescription>
                  Landed unit cost includes the pro-rata or line-specific costs below.
                </CardDescription>
              </CardHeading>
            </CardHeader>
            <CardContent>
              <Table bare>
                <TableHeader>
                  <TableRow>
                    <TableHead>Description</TableHead>
                    <TableHead className="text-right">Quantity</TableHead>
                    <TableHead className="text-right">Allocated</TableHead>
                    <TableHead className="text-right">Landed unit</TableHead>
                    <TableHead className="text-right">Sale unit</TableHead>
                    <TableHead className="text-right">Line margin</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(results.lines ?? []).map((line) => (
                    <TableRow key={line.product_id}>
                      <TableCell className="max-w-[260px] truncate text-[12px] text-mist-100">
                        {line.description}
                      </TableCell>
                      <TableCell className="text-right text-[11.5px] text-mist-300">
                        {formatQuantity(line.quantity, line.unit)}
                      </TableCell>
                      <TableCell className="text-right text-[11.5px] text-mist-300">
                        {formatMoney(line.allocated_cost, currency)}
                      </TableCell>
                      <TableCell className="text-right text-[11.5px] text-mist-200">
                        {formatMoney(line.landed_unit_cost, currency)}
                      </TableCell>
                      <TableCell className="text-right text-[11.5px] text-mist-100">
                        {formatMoney(line.unit_sale_price, currency)}
                      </TableCell>
                      <TableCell className="text-right text-[11.5px] text-mist-300">
                        {formatMoney(line.line_margin, currency)}
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
                <CardTitle>Cost components</CardTitle>
                <CardDescription>
                  Every cost carries its source and whether it was estimated or verified.
                </CardDescription>
              </CardHeading>
            </CardHeader>
            <CardContent>
              <Table bare>
                <TableHeader>
                  <TableRow>
                    <TableHead>Type</TableHead>
                    <TableHead>Source</TableHead>
                    <TableHead>Basis</TableHead>
                    <TableHead>Verification</TableHead>
                    <TableHead className="text-right">Amount</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {record.components.map((component) => (
                    <TableRow key={component.id}>
                      <TableCell className="text-[11.5px] text-mist-100">
                        {component.cost_type.replaceAll("_", " ")}
                        {component.product_sku ? (
                          <span className="ml-1 font-mono text-[10px] text-mist-500">
                            {component.product_sku}
                          </span>
                        ) : null}
                      </TableCell>
                      <TableCell className="max-w-[220px] truncate text-[11px] text-mist-400">
                        {component.source_reference}
                      </TableCell>
                      <TableCell className="text-[11px] text-mist-400">{component.basis}</TableCell>
                      <TableCell className="text-[11px]">
                        <Badge
                          variant={
                            component.verification_status === "VERIFIED" ? "success" : "warning"
                          }
                        >
                          {component.verification_status}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right whitespace-nowrap text-[11.5px] text-mist-200">
                        {formatMoney(component.amount, component.currency)}
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
                <CardTitle>Draft a sales quote</CardTitle>
                <CardDescription>
                  Prices come from this scenario. Submission needs verified inputs.
                </CardDescription>
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
                <Alert variant="info" title="Read-only access">
                  Drafting a sales quote requires <span className="font-mono">trade.write</span>.
                </Alert>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>Completeness</CardTitle>
                <CardDescription>What the engine knew when it calculated.</CardDescription>
              </CardHeading>
            </CardHeader>
            <CardContent>
              <dl className="space-y-2 text-[11.5px]">
                <div>
                  <dt className="eyebrow">Lines / components</dt>
                  <dd className="text-mist-200">
                    {String(record.completeness.line_count ?? "—")} lines ·{" "}
                    {String(record.completeness.component_count ?? "—")} costs
                  </dd>
                </div>
                <div>
                  <dt className="eyebrow">Estimated components</dt>
                  <dd className="text-mist-200">
                    {String(record.completeness.estimated_component_count ?? "—")}
                  </dd>
                </div>
                <div>
                  <dt className="eyebrow">Realised margin / markup</dt>
                  <dd className="text-mist-200">
                    {formatPercent(String(record.completeness.realised_margin_pct ?? ""))} /{" "}
                    {formatPercent(String(record.completeness.realised_markup_pct ?? ""))}
                  </dd>
                </div>
              </dl>
            </CardContent>
          </Card>

          <Link
            href={`/quotes/${record.supplier_quote_id}`}
            className="inline-flex text-[12px] text-accent-200 hover:text-accent-100"
          >
            Open the supplier quote behind this scenario
          </Link>
        </div>
      </div>
    </div>
  );
}
