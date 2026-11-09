import { LOCALE_COOKIE } from "./locale-cookie";
import { normalizeLocale, translate, type Locale, type MessageKey } from "./messages";

/**
 * The language of the page this code runs in, for code that has no React context (the API
 * clients). The root layout sets `<html lang>` from the language cookie, so in a browser it is
 * always the language the person sees; anywhere else it is English.
 */
export function browserLocale(): Locale {
  if (typeof document === "undefined") return "en";
  return normalizeLocale(document.documentElement.lang);
}

export function browserT(key: MessageKey, params?: Record<string, string | number>): string {
  return translate(browserLocale(), key, params);
}

/** The language in a `Cookie` header, for route handlers. */
export function localeFromCookieHeader(header: string | null | undefined): Locale {
  const entry = header
    ?.split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(`${LOCALE_COOKIE}=`));
  return normalizeLocale(entry?.slice(LOCALE_COOKIE.length + 1));
}
