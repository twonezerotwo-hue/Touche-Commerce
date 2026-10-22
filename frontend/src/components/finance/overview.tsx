import { Banknote, Building2, Coins, Database, Landmark, ReceiptText } from "lucide-react";

import { FinanceStatusBadge } from "@/components/finance/status-badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardHeading,
  CardTitle,
} from "@/components/ui/card";
import { Stat } from "@/components/ui/stat";
import { formatFinanceMoney } from "@/lib/finance/format";
import type { FinanceStatus, FinanceSummary } from "@/lib/finance/types";
import { formatDate, formatTimestamp } from "@/lib/trade/format";

export interface FinanceOverviewProps {
  status: FinanceStatus;
  summary: FinanceSummary | null;
}

function money(value: { amount: string } | undefined, currency: string | null): string {
  if (!value) return "—";
  return formatFinanceMoney(value, currency);
}

/** Read-only Finance truth, including every state in which data is not current. */
export function FinanceOverview({ status, summary }: FinanceOverviewProps) {
  const mapping = status.mapping;
  const currencies = status.available_currencies ?? [];
  const currency = summary?.currency ?? null;
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardHeading>
            <div className="flex flex-wrap items-center gap-2">
              <CardTitle>Finance connection</CardTitle>
              <FinanceStatusBadge state={status.state} />
            </div>
            <CardDescription>{status.detail}</CardDescription>
          </CardHeading>
          <p className="font-mono text-[10px] whitespace-nowrap text-mist-600">
            checked {formatTimestamp(status.checked_at)}
          </p>
        </CardHeader>
        <CardContent className="grid gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <p className="eyebrow flex items-center gap-1.5">
              <Building2 className="size-3" aria-hidden /> Mapped company
            </p>
            <p className="mt-1 text-[12.5px] text-mist-200">
              {mapping?.finance_company_name ?? mapping?.finance_company_id ?? "Not configured"}
            </p>
            {mapping?.finance_company_id ? (
              <p className="mt-0.5 font-mono text-[10px] text-mist-600">
                {mapping.finance_company_id}
              </p>
            ) : null}
          </div>
          <div>
            <p className="eyebrow flex items-center gap-1.5">
              <Coins className="size-3" aria-hidden /> Currencies
            </p>
            <p className="mt-1 text-[12.5px] text-mist-200">
              {currencies.length > 0 ? currencies.join(" · ") : "Not reported"}
            </p>
            <p className="mt-0.5 text-[10px] text-mist-600">
              One currency per request; no conversion or aggregation.
            </p>
          </div>
          <div>
            <p className="eyebrow flex items-center gap-1.5">
              <Database className="size-3" aria-hidden /> Data through
            </p>
            <p className="mt-1 text-[12.5px] text-mist-200">
              {formatDate(status.data_through ?? null)}
            </p>
            <p className="mt-0.5 text-[10px] text-mist-600">Finance ledger watermark</p>
          </div>
          <div>
            <p className="eyebrow flex items-center gap-1.5">
              <Landmark className="size-3" aria-hidden /> Finance health
            </p>
            <p className="mt-1 text-[12.5px] text-mist-200">
              {status.finance_status ?? "Not reported"}
            </p>
            <p className="mt-0.5 text-[10px] text-mist-600">
              {status.latency_ms.toFixed(1)} ms · read-only
            </p>
          </div>
        </CardContent>
      </Card>

      {summary ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          <Stat
            label="Cash"
            value={money(summary.balances.cash, currency)}
            detail={`Finance account summary · ${summary.ledger.document_count} documents`}
            icon={<Banknote className="size-4" aria-hidden />}
          />
          <Stat
            label="Receivables"
            value={money(summary.balances.receivables, currency)}
            detail={`${summary.ledger.line_count} ledger lines`}
            icon={<ReceiptText className="size-4" aria-hidden />}
            tone="jade"
          />
          <Stat
            label="Payables"
            value={money(summary.balances.payables, currency)}
            detail={`As of ${formatDate(summary.as_of ?? null)}`}
            icon={<ReceiptText className="size-4" aria-hidden />}
            tone="amber"
          />
          <Stat
            label="Revenue"
            value={money(summary.balances.revenue, currency)}
            detail="Finance ledger · no inferred revenue"
          />
          <Stat
            label="Cost"
            value={money(summary.balances.cost, currency)}
            detail="Finance ledger · no inferred cost"
          />
          <Stat
            label="Gross profit"
            value={money(summary.balances.gross_profit, currency)}
            detail="Finance's engine values, passed through"
            tone="jade"
          />
        </div>
      ) : (
        <Card variant="inset">
          <CardContent className="py-4 text-[12px] text-mist-400">
            No Finance summary is loaded. Select a currency when Finance reports more than one;
            Commerce never derives a balance from another currency.
          </CardContent>
        </Card>
      )}

      <div className="panel px-4 py-3 text-[11px] leading-relaxed text-mist-500">
        Invoices and payments are <span className="text-mist-300">Not available</span>. Finance
        exposes no structured invoice or payment objects, so Commerce does not fabricate invoice
        statuses, payment states or settlement dates.
      </div>
    </div>
  );
}
