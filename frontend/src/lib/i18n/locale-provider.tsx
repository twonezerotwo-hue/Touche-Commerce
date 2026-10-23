"use client";

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useSyncExternalStore,
  type ReactNode,
} from "react";

import { normalizeLocale, translate, type Locale, type MessageKey } from "./messages";

const STORAGE_KEY = "touche.commerce.locale";
const LOCALE_EVENT = "touche-commerce-locale-changed";

export interface LocaleContextValue {
  locale: Locale;
  changeLocale: (next: Locale) => void;
  t: (key: MessageKey) => string;
}

const FALLBACK: LocaleContextValue = {
  locale: "en",
  changeLocale: () => undefined,
  t: (key) => translate("en", key),
};

const LocaleContext = createContext<LocaleContextValue>(FALLBACK);

function readLocale(): Locale {
  try {
    return normalizeLocale(window.localStorage.getItem(STORAGE_KEY));
  } catch {
    return "en";
  }
}

function subscribe(callback: () => void): () => void {
  window.addEventListener("storage", callback);
  window.addEventListener(LOCALE_EVENT, callback);
  return () => {
    window.removeEventListener("storage", callback);
    window.removeEventListener(LOCALE_EVENT, callback);
  };
}

/** Same server snapshot on SSR and first hydration to avoid mismatches. */
function serverSnapshot(): Locale {
  return "en";
}

export function LocaleProvider({ children }: { children: ReactNode }) {
  const locale = useSyncExternalStore(subscribe, readLocale, serverSnapshot);

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const context = useMemo<LocaleContextValue>(
    () => ({
      locale,
      changeLocale(next) {
        try {
          window.localStorage.setItem(STORAGE_KEY, normalizeLocale(next));
        } catch {
          // Private-browser storage can be unavailable; no sensitive data is stored.
        }
        window.dispatchEvent(new Event(LOCALE_EVENT));
      },
      t(key) {
        return translate(locale, key);
      },
    }),
    [locale],
  );

  return <LocaleContext.Provider value={context}>{children}</LocaleContext.Provider>;
}

export function useLocale(): LocaleContextValue {
  return useContext(LocaleContext);
}
