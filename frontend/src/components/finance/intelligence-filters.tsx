"use client";

import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import {
  hasActiveFilters,
  humanize,
  type IntelligenceFilterOptions,
  type IntelligenceFilters,
} from "@/lib/finance/intelligence";
import { completenessWord, modelWord, statusWord } from "@/lib/finance/intelligence-text";
import { useLocale } from "@/lib/i18n/locale-provider";
import { reconciliationStatusText } from "@/lib/i18n/value-labels";

function Field({ id, label, children }: { id: string; label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="eyebrow block">
        {label}
      </label>
      {children}
    </div>
  );
}

function OptionSelect({
  name,
  label,
  value,
  allLabel,
  options,
  width = "w-[150px]",
}: {
  name: string;
  label: string;
  value: string | undefined;
  allLabel: string;
  options: ReadonlyArray<{ value: string; label: string }>;
  width?: string;
}) {
  const id = `intelligence-${name}`;
  return (
    <Field id={id} label={label}>
      <Select id={id} name={name} defaultValue={value ?? ""} className={`h-8 text-[12px] ${width}`}>
        <option value="">{allLabel}</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </Select>
    </Field>
  );
}

/**
 * Explicit GET filters shared by the intelligence screens. Options come from the
 * backend (`filter_options`), so a selectable value always exists in the data.
 */
export function IntelligenceFilterBar({
  action,
  filters,
  options,
  hidden = {},
}: {
  action: string;
  filters: IntelligenceFilters;
  options: IntelligenceFilterOptions;
  /** Non-filter state (for example the active tab) preserved across Apply. */
  hidden?: Record<string, string>;
}) {
  const { t, locale } = useLocale();
  const plain = (values: readonly string[], words: (value: string) => string = humanize) =>
    values.map((value) => ({ value, label: words(value) }));
  const reconciliationWord = (value: string): string =>
    locale === "tr" ? reconciliationStatusText(t, value) : humanize(value);
  return (
    <form action={action} method="get" className="panel flex flex-wrap items-end gap-2 px-4 py-3">
      {Object.entries(hidden).map(([name, value]) => (
        <input key={name} type="hidden" name={name} value={value} />
      ))}
      <Field id="intelligence-from" label={t("intFilterFrom")}>
        <Input
          id="intelligence-from"
          name="from"
          type="date"
          defaultValue={filters.from ?? ""}
          className="h-8 w-[145px] text-[12px]"
        />
      </Field>
      <Field id="intelligence-to" label={t("intFilterTo")}>
        <Input
          id="intelligence-to"
          name="to"
          type="date"
          defaultValue={filters.to ?? ""}
          className="h-8 w-[145px] text-[12px]"
        />
      </Field>
      <OptionSelect
        name="currency"
        label={t("intFilterCurrency")}
        value={filters.currency}
        allLabel={t("intFilterAllCurrencies")}
        options={plain(options.currencies)}
        width="w-[120px]"
      />
      <OptionSelect
        name="fulfilment_model"
        label={t("intFilterModel")}
        value={filters.fulfilment_model}
        allLabel={t("intFilterAllModels")}
        options={plain(options.fulfilment_models, (value) => modelWord(t, locale, value))}
        width="w-[170px]"
      />
      <OptionSelect
        name="order_status"
        label={t("intFilterOrderStatus")}
        value={filters.order_status}
        allLabel={t("intFilterAllStatuses")}
        options={plain(options.order_statuses, (value) => statusWord(t, locale, value))}
      />
      <OptionSelect
        name="customer_id"
        label={t("intFilterCustomer")}
        value={filters.customer_id}
        allLabel={t("intFilterAllCustomers")}
        options={options.customers.map((item) => ({ value: item.id, label: item.name }))}
        width="w-[190px]"
      />
      <OptionSelect
        name="supplier_id"
        label={t("intFilterSupplier")}
        value={filters.supplier_id}
        allLabel={t("intFilterAllSuppliers")}
        options={options.suppliers.map((item) => ({ value: item.id, label: item.name }))}
        width="w-[190px]"
      />
      <OptionSelect
        name="reconciliation_status"
        label={t("intFilterReconciliation")}
        value={filters.reconciliation_status}
        allLabel={t("intFilterAny")}
        options={plain(options.reconciliation_statuses, reconciliationWord)}
        width="w-[170px]"
      />
      <OptionSelect
        name="completeness"
        label={t("intFilterCompleteness")}
        value={filters.completeness}
        allLabel={t("intFilterAny")}
        options={plain(options.completeness_statuses, (value) =>
          locale === "tr" ? completenessWord(t, value as never) : humanize(value),
        )}
      />
      <Button type="submit" size="sm" variant="subtle">
        {t("intApply")}
      </Button>
      {hasActiveFilters(filters) ? (
        <Button asChild size="sm" variant="ghost">
          <Link
            href={
              Object.keys(hidden).length > 0
                ? `${action}?${new URLSearchParams(hidden).toString()}`
                : action
            }
          >
            {t("intClear")}
          </Link>
        </Button>
      ) : null}
    </form>
  );
}
