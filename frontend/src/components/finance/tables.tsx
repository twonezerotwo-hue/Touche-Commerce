import { FileSearch } from "lucide-react";

import { EmptyState } from "@/components/ui/empty-state";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatFinanceMoney } from "@/lib/finance/format";
import type { FinanceAccounts, FinanceAging } from "@/lib/finance/types";
import { formatDate } from "@/lib/trade/format";

export function FinanceAccountsTable({ data }: { data: FinanceAccounts }) {
  if (data.accounts.length === 0) {
    return (
      <EmptyState
        icon={<FileSearch className="size-5" aria-hidden />}
        title="No accounts returned"
        description="Finance returned no account movement for this currency and date range."
      />
    );
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Account</TableHead>
          <TableHead>Name</TableHead>
          <TableHead>Type</TableHead>
          <TableHead className="text-right">Debit</TableHead>
          <TableHead className="text-right">Credit</TableHead>
          <TableHead className="text-right">Balance</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {data.accounts.map((account) => (
          <TableRow key={account.account_code}>
            <TableCell className="font-mono text-[11.5px] text-accent-200">
              {account.account_code}
            </TableCell>
            <TableCell className="text-mist-200">{account.name}</TableCell>
            <TableCell className="text-[10.5px] tracking-[0.04em] text-mist-500 uppercase">
              {account.type}
            </TableCell>
            <TableCell className="text-right font-mono text-[11.5px]">
              {formatFinanceMoney(account.debit, data.currency ?? null)}
            </TableCell>
            <TableCell className="text-right font-mono text-[11.5px]">
              {formatFinanceMoney(account.credit, data.currency ?? null)}
            </TableCell>
            <TableCell className="text-right font-mono text-[11.5px] text-mist-100">
              {formatFinanceMoney(account.balance, data.currency ?? null)}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

export function FinanceAgingTable({ data }: { data: FinanceAging }) {
  if (data.items.length === 0) {
    return (
      <EmptyState
        icon={<FileSearch className="size-5" aria-hidden />}
        title={`No ${data.type === "receivable" ? "receivable" : "payable"} aging items`}
        description={`Finance returned no open ${data.type} documents for this currency and date.`}
      />
    );
  }
  const currency = data.currency ?? null;
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Counterparty</TableHead>
          <TableHead className="text-right">Not due</TableHead>
          <TableHead className="text-right">1–30</TableHead>
          <TableHead className="text-right">31–60</TableHead>
          <TableHead className="text-right">61–90</TableHead>
          <TableHead className="text-right">&gt; 90</TableHead>
          <TableHead className="text-right">Total</TableHead>
          <TableHead>Open source documents</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {data.items.map((item, index) => (
          <TableRow key={`${item.counterparty}-${index}`}>
            <TableCell className="text-mist-200">
              {item.counterparty}
              <span className="mt-0.5 block text-[10px] text-mist-600">
                Free-text ledger.cari, not a master key
              </span>
            </TableCell>
            <TableCell className="text-right font-mono text-[11px]">
              {formatFinanceMoney(item.buckets.not_due, currency)}
            </TableCell>
            <TableCell className="text-right font-mono text-[11px]">
              {formatFinanceMoney(item.buckets.days_1_30, currency)}
            </TableCell>
            <TableCell className="text-right font-mono text-[11px]">
              {formatFinanceMoney(item.buckets.days_31_60, currency)}
            </TableCell>
            <TableCell className="text-right font-mono text-[11px]">
              {formatFinanceMoney(item.buckets.days_61_90, currency)}
            </TableCell>
            <TableCell className="text-right font-mono text-[11px]">
              {formatFinanceMoney(item.buckets.days_over_90, currency)}
            </TableCell>
            <TableCell className="text-right font-mono text-[11.5px] text-mist-100">
              {formatFinanceMoney(item.total, currency)}
            </TableCell>
            <TableCell className="max-w-[280px]">
              {item.open_items.length > 0 ? (
                <ul className="space-y-1">
                  {item.open_items.map((open) => (
                    <li
                      key={open.source_id}
                      className="font-mono text-[10.5px] leading-relaxed text-mist-400"
                    >
                      {open.source_id} · due {formatDate(open.due_date ?? null)} ·{" "}
                      {formatFinanceMoney(open.remaining, currency)}
                    </li>
                  ))}
                </ul>
              ) : (
                <span className="text-[10.5px] text-mist-600">No open documents</span>
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
