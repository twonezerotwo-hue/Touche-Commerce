import type { Locale } from "@/lib/i18n/messages";
import { formatMoney } from "@/lib/trade/format";

/** Format a Finance source amount; never converts or re-rounds it. */
export function formatFinanceMoney(
  value: { amount: string } | undefined,
  currency: string | null,
  locale: Locale = "en",
): string {
  if (!value) return "—";
  return formatMoney(value.amount, currency ?? "USD", locale);
}

/** Format a decimal string; unavailable remains words, never a fabricated zero. */
export function formatReconciliationMoney(
  value: string | null | undefined,
  currency: string | null,
  unavailable = "Not available",
  locale: Locale = "en",
): string {
  if (value === null || value === undefined) return unavailable;
  return formatMoney(value, currency ?? "USD", locale);
}

/**
 * A percentage value already computed by the backend, or an explicit gap. The digits are the
 * backend's; Turkish only moves the sign and uses a decimal comma.
 */
export function formatReconciliationPercent(
  value: string | null | undefined,
  unavailable = "Not available",
  locale: Locale = "en",
): string {
  if (value === null || value === undefined) return unavailable;
  return locale === "tr" ? `%${value.replace(".", ",")}` : `${value}%`;
}
