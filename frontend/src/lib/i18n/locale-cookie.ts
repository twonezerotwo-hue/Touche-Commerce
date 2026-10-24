/**
 * The interface language is a cookie so server components can render the right language
 * on the first byte (no flash, no hydration mismatch). It holds only "en" or "tr": no
 * identity, no session, no trade data.
 */

export const LOCALE_COOKIE = "touche_locale";
const ONE_YEAR_SECONDS = 60 * 60 * 24 * 365;

export function serializeLocaleCookie(locale: "en" | "tr", secure: boolean): string {
  const parts = [
    `${LOCALE_COOKIE}=${locale}`,
    "Path=/",
    `Max-Age=${ONE_YEAR_SECONDS}`,
    "SameSite=Lax",
  ];
  if (secure) parts.push("Secure");
  return parts.join("; ");
}
