import { formatMoney } from "@/lib/trade/format";

/** Format a Finance source amount; never converts or re-rounds it. */
export function formatFinanceMoney(
  value: { amount: string } | undefined,
  currency: string | null,
): string {
  if (!value) return "—";
  return formatMoney(value.amount, currency ?? "USD");
}
