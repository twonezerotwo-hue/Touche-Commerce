import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import type { FinanceView } from "@/lib/finance/types";

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
  return (
    <form action="/finance" method="get" className="flex flex-wrap items-end gap-2">
      <div className="space-y-1">
        <label htmlFor="finance-view" className="eyebrow">
          View
        </label>
        <Select
          id="finance-view"
          name="view"
          defaultValue={view}
          className="h-8 w-[155px] text-[12px]"
        >
          <option value="overview">Overview</option>
          <option value="accounts">Accounts</option>
          <option value="receivables">Receivables</option>
          <option value="payables">Payables</option>
        </Select>
      </div>
      <div className="space-y-1">
        <label htmlFor="finance-currency" className="eyebrow">
          Currency
        </label>
        <Select
          id="finance-currency"
          name="currency"
          defaultValue={currency}
          className="h-8 w-[110px] text-[12px]"
        >
          <option value="">Select currency</option>
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
              From
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
              To
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
            As of
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
        Apply
      </Button>
    </form>
  );
}
