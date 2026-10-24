"use client";

import { useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { serializeLocaleCookie } from "./locale-cookie";
import { normalizeLocale, translate, type Locale, type MessageKey } from "./messages";

/** Choice made before the cookie existed (Stage 12A); migrated once, then ignored. */
const LEGACY_STORAGE_KEY = "touche.commerce.locale";

export type Translate = (key: MessageKey, params?: Record<string, string | number>) => string;

export interface LocaleContextValue {
  locale: Locale;
  changeLocale: (next: Locale) => void;
  t: Translate;
}

const FALLBACK: LocaleContextValue = {
  locale: "en",
  changeLocale: () => undefined,
  t: (key, params) => translate("en", key, params),
};

const LocaleContext = createContext<LocaleContextValue>(FALLBACK);

function writeCookie(locale: Locale): void {
  document.cookie = serializeLocaleCookie(locale, window.location.protocol === "https:");
}

/**
 * ``initialLocale`` comes from the cookie on the server, so the first render is already in
 * the right language. Changing it writes the cookie and refreshes the route, which makes
 * server components render again in the new language.
 */
export function LocaleProvider({
  children,
  initialLocale = "en",
}: {
  children: ReactNode;
  initialLocale?: Locale;
}) {
  const router = useRouter();
  // The server decides the language (cookie). When a refresh brings a new value, follow it:
  // derived state, adjusted while rendering, not in an effect.
  const [state, setState] = useState<{ initial: Locale; locale: Locale }>({
    initial: initialLocale,
    locale: initialLocale,
  });
  if (state.initial !== initialLocale) {
    setState({ initial: initialLocale, locale: initialLocale });
  }
  const locale = state.locale;

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  // One-time migration of a Stage 12A browser-only preference into the cookie.
  useEffect(() => {
    if (initialLocale !== "en") return;
    try {
      const legacy = window.localStorage.getItem(LEGACY_STORAGE_KEY);
      if (legacy === "tr" && !document.cookie.includes("touche_locale=")) {
        writeCookie("tr");
        window.localStorage.removeItem(LEGACY_STORAGE_KEY);
        router.refresh();
      }
    } catch {
      // Storage can be unavailable in private windows; the choice simply is not migrated.
    }
  }, [initialLocale, router]);

  const changeLocale = useCallback(
    (next: Locale) => {
      const normalised = normalizeLocale(next);
      writeCookie(normalised);
      setState((current) => ({ ...current, locale: normalised }));
      router.refresh();
    },
    [router],
  );

  const context = useMemo<LocaleContextValue>(
    () => ({
      locale,
      changeLocale,
      t: (key, params) => translate(locale, key, params),
    }),
    [locale, changeLocale],
  );

  return <LocaleContext.Provider value={context}>{children}</LocaleContext.Provider>;
}

export function useLocale(): LocaleContextValue {
  return useContext(LocaleContext);
}
