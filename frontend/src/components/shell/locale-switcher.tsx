"use client";

import { Globe2 } from "lucide-react";

import { useLocale } from "@/lib/i18n/locale-provider";
import { normalizeLocale } from "@/lib/i18n/messages";

/** Per-browser locale preference; never stores an account token or user profile. */
export function LocaleSwitcher() {
  const { locale, changeLocale, t } = useLocale();

  return (
    <label className="inline-flex min-h-8 items-center gap-1.5 rounded-md border border-white/[0.08] bg-white/[0.025] px-2 text-mist-300">
      <Globe2 className="size-3.5 shrink-0 text-mist-500" aria-hidden />
      <span className="sr-only">{t("language")}</span>
      <select
        aria-label={t("language")}
        value={locale}
        onChange={(event) => changeLocale(normalizeLocale(event.target.value))}
        className="cursor-pointer bg-transparent text-[11px] font-medium text-mist-200 outline-none"
      >
        <option value="en" className="bg-ink-900 text-mist-100">
          EN
        </option>
        <option value="tr" className="bg-ink-900 text-mist-100">
          TR
        </option>
      </select>
    </label>
  );
}
