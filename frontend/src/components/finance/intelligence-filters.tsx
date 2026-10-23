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

function Field({ id, label, children }: { id: string; label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="eyebrow">
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
  const plain = (values: readonly string[]) =>
    values.map((value) => ({ value, label: humanize(value) }));
  return (
    <form action={action} method="get" className="panel flex flex-wrap items-end gap-2 px-4 py-3">
      {Object.entries(hidden).map(([name, value]) => (
        <input key={name} type="hidden" name={name} value={value} />
      ))}
      <Field id="intelligence-from" label="From">
        <Input
          id="intelligence-from"
          name="from"
          type="date"
          defaultValue={filters.from ?? ""}
          className="h-8 w-[145px] text-[12px]"
        />
      </Field>
      <Field id="intelligence-to" label="To">
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
        label="Currency"
        value={filters.currency}
        allLabel="All currencies"
        options={plain(options.currencies)}
        width="w-[120px]"
      />
      <OptionSelect
        name="fulfilment_model"
        label="Model"
        value={filters.fulfilment_model}
        allLabel="All models"
        options={plain(options.fulfilment_models)}
        width="w-[170px]"
      />
      <OptionSelect
        name="order_status"
        label="Order status"
        value={filters.order_status}
        allLabel="All statuses"
        options={plain(options.order_statuses)}
      />
      <OptionSelect
        name="customer_id"
        label="Customer"
        value={filters.customer_id}
        allLabel="All customers"
        options={options.customers.map((item) => ({ value: item.id, label: item.name }))}
        width="w-[190px]"
      />
      <OptionSelect
        name="supplier_id"
        label="Supplier"
        value={filters.supplier_id}
        allLabel="All suppliers"
        options={options.suppliers.map((item) => ({ value: item.id, label: item.name }))}
        width="w-[190px]"
      />
      <OptionSelect
        name="reconciliation_status"
        label="Reconciliation"
        value={filters.reconciliation_status}
        allLabel="Any"
        options={plain(options.reconciliation_statuses)}
        width="w-[170px]"
      />
      <OptionSelect
        name="completeness"
        label="Completeness"
        value={filters.completeness}
        allLabel="Any"
        options={plain(options.completeness_statuses)}
      />
      <Button type="submit" size="sm" variant="subtle">
        Apply
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
            Clear
          </Link>
        </Button>
      ) : null}
    </form>
  );
}
