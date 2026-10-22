import { formatMoney } from "@/lib/trade/format";

/** Format a Finance source amount; never converts or re-rounds it. */
export function formatFinanceMoney(
  value: { amount: string } | undefined,
  currency: string | null,
): string {
  if (!value) return "—";
  return formatMoney(value.amount, currency ?? "USD");
}

/** Format a decimal string; unavailable remains words, never a fabricated zero. */
export function formatReconciliationMoney(
  value: string | null | undefined,
  currency: string | null,
  unavailable = "Not available",
): string {
  if (value === null || value === undefined) return unavailable;
  return formatMoney(value, currency ?? "USD");
}

/** A percentage value already computed by the backend, or an explicit gap. */
export function formatReconciliationPercent(value: string | null | undefined): string {
  return value === null || value === undefined ? "Not available" : `${value}%`;
}
