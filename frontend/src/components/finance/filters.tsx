"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import type { FinanceView } from "@/lib/finance/types";
import { useLocale } from "@/lib/i18n/locale-provider";

export interface FinanceFiltersProps {
  currencies: string[];
  view: FinanceView;
  currency: string;
  fromDate: string;
  toDate: string;
  asOf: string;
}

/** Explicit GET filters; the browser never sends a company or Finance key. */
export function FinanceFilters({
  currencies,
  view,
  currency,
  fromDate,
  toDate,
  asOf,
}: FinanceFiltersProps) {
  const { t } = useLocale();
  return (
    <form action="/finance" method="get" className="flex flex-wrap items-end gap-2">
      <div className="space-y-1">
        <label htmlFor="finance-view" className="eyebrow">
          {t("finFilterView")}
        </label>
        <Select
          id="finance-view"
          name="view"
          defaultValue={view}
          className="h-8 w-[155px] text-[12px]"
        >
          <option value="overview">{t("finTabOverview")}</option>
          <option value="accounts">{t("finTabAccounts")}</option>
          <option value="receivables">{t("finTabReceivables")}</option>
          <option value="payables">{t("finTabPayables")}</option>
        </Select>
      </div>
      <div className="space-y-1">
        <label htmlFor="finance-currency" className="eyebrow">
          {t("finFilterCurrency")}
        </label>
        <Select
          id="finance-currency"
          name="currency"
          defaultValue={currency}
          className="h-8 w-[110px] text-[12px]"
        >
          <option value="">{t("finFilterSelectCurrency")}</option>
          {currencies.map((code) => (
            <option key={code} value={code}>
              {code}
            </option>
          ))}
        </Select>
      </div>
      {view === "accounts" ? (
        <>
          <div className="space-y-1">
            <label htmlFor="finance-from" className="eyebrow">
              {t("finFilterFrom")}
            </label>
            <Input
              id="finance-from"
              name="from"
              type="date"
              defaultValue={fromDate}
              className="h-8 w-[145px] text-[12px]"
            />
          </div>
          <div className="space-y-1">
            <label htmlFor="finance-to" className="eyebrow">
              {t("finFilterTo")}
            </label>
            <Input
              id="finance-to"
              name="to"
              type="date"
              defaultValue={toDate}
              className="h-8 w-[145px] text-[12px]"
            />
          </div>
        </>
      ) : null}
      {view === "receivables" || view === "payables" ? (
        <div className="space-y-1">
          <label htmlFor="finance-as-of" className="eyebrow">
            {t("finFilterAsOf")}
          </label>
          <Input
            id="finance-as-of"
            name="as_of"
            type="date"
            defaultValue={asOf}
            className="h-8 w-[145px] text-[12px]"
          />
        </div>
      ) : null}
      <Button type="submit" size="sm" variant="subtle">
        {t("finApply")}
      </Button>
    </form>
  );
}
