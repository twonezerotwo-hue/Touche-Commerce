"use client";

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
import { useLocale } from "@/lib/i18n/locale-provider";
import { formatDate } from "@/lib/trade/format";

export function FinanceAccountsTable({ data }: { data: FinanceAccounts }) {
  const { t, locale } = useLocale();
  if (data.accounts.length === 0) {
    return (
      <EmptyState
        icon={<FileSearch className="size-5" aria-hidden />}
        title={t("finNoAccountsTitle")}
        description={t("finNoAccountsBody")}
      />
    );
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{t("finColAccount")}</TableHead>
          <TableHead>{t("finColName")}</TableHead>
          <TableHead>{t("finColType")}</TableHead>
          <TableHead className="text-right">{t("finColDebit")}</TableHead>
          <TableHead className="text-right">{t("finColCredit")}</TableHead>
          <TableHead className="text-right">{t("finColBalance")}</TableHead>
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
              {formatFinanceMoney(account.debit, data.currency ?? null, locale)}
            </TableCell>
            <TableCell className="text-right font-mono text-[11.5px]">
              {formatFinanceMoney(account.credit, data.currency ?? null, locale)}
            </TableCell>
            <TableCell className="text-right font-mono text-[11.5px] text-mist-100">
              {formatFinanceMoney(account.balance, data.currency ?? null, locale)}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

export function FinanceAgingTable({ data }: { data: FinanceAging }) {
  const { t, locale } = useLocale();
  if (data.items.length === 0) {
    const receivable = data.type === "receivable";
    return (
      <EmptyState
        icon={<FileSearch className="size-5" aria-hidden />}
        title={receivable ? t("finNoReceivableTitle") : t("finNoPayableTitle")}
        description={receivable ? t("finNoReceivableBody") : t("finNoPayableBody")}
      />
    );
  }
  const currency = data.currency ?? null;
  const money = (value: { amount: string } | undefined) =>
    formatFinanceMoney(value, currency, locale);
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{t("finColCounterparty")}</TableHead>
          <TableHead className="text-right">{t("finColNotDue")}</TableHead>
          <TableHead className="text-right">1–30</TableHead>
          <TableHead className="text-right">31–60</TableHead>
          <TableHead className="text-right">61–90</TableHead>
          <TableHead className="text-right">&gt; 90</TableHead>
          <TableHead className="text-right">{t("finColTotal")}</TableHead>
          <TableHead>{t("finColOpenDocs")}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {data.items.map((item, index) => (
          <TableRow key={`${item.counterparty}-${index}`}>
            <TableCell className="text-mist-200">
              {item.counterparty}
              <span className="mt-0.5 block text-[10px] text-mist-600">{t("finFreeTextNote")}</span>
            </TableCell>
            <TableCell className="text-right font-mono text-[11px]">
              {money(item.buckets.not_due)}
            </TableCell>
            <TableCell className="text-right font-mono text-[11px]">
              {money(item.buckets.days_1_30)}
            </TableCell>
            <TableCell className="text-right font-mono text-[11px]">
              {money(item.buckets.days_31_60)}
            </TableCell>
            <TableCell className="text-right font-mono text-[11px]">
              {money(item.buckets.days_61_90)}
            </TableCell>
            <TableCell className="text-right font-mono text-[11px]">
              {money(item.buckets.days_over_90)}
            </TableCell>
            <TableCell className="text-right font-mono text-[11.5px] text-mist-100">
              {money(item.total)}
            </TableCell>
            <TableCell className="max-w-[280px]">
              {item.open_items.length > 0 ? (
                <ul className="space-y-1">
                  {item.open_items.map((open) => (
                    <li
                      key={open.source_id}
                      className="font-mono text-[10.5px] leading-relaxed text-mist-400"
                    >
                      {t("finOpenItem", {
                        id: open.source_id,
                        date: formatDate(open.due_date ?? null, locale),
                        amount: money(open.remaining),
                      })}
                    </li>
                  ))}
                </ul>
              ) : (
                <span className="text-[10.5px] text-mist-600">{t("finNoOpenDocs")}</span>
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
