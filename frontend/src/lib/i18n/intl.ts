import type { Locale } from "./messages";

/**
 * The BCP 47 tag used for numbers and dates. Locale, currency and time zone are three separate
 * choices: the locale only decides separators and month names, the currency is the ISO code stored
 * with the amount, and instants are always shown in UTC (there is no per-company time zone yet).
 */
export function intlTag(locale: Locale): string {
  return locale === "tr" ? "tr-TR" : "en-GB";
}
