/**
 * Type-safe English/Turkish interface vocabulary.
 *
 * The catalogue is split by area (`catalog/*`) and merged here. Every area declares its
 * Turkish text as `Record<keyof typeof english, string>`, so a missing translation is a
 * compile error, not a runtime surprise. Trade records (names, notes, quoted text) are
 * never translated: only interface text is.
 */

import { authEn, authTr } from "./catalog/auth";
import { commonEn, commonTr } from "./catalog/common";
import { dashboardEn, dashboardTr } from "./catalog/dashboard";
import { dealsEn, dealsTr } from "./catalog/deals";
import { documentsEn, documentsTr } from "./catalog/documents";
import { importsEn, importsTr } from "./catalog/imports";
import { tradeEn, tradeTr } from "./catalog/trade";

export const SUPPORTED_LOCALES = ["en", "tr"] as const;
export type Locale = (typeof SUPPORTED_LOCALES)[number];

const shellEn = {
  workspace: "Workspace",
  sessionVerified: "Session verified",
  systemStatus: "System status",
  profileAccess: "Profile and access",
  language: "Interface language",
  english: "English",
  turkish: "Türkçe",
  openNavigation: "Open navigation",
  closeNavigation: "Close navigation",
  mobilePrimary: "Mobile primary navigation",
  platform: "Platform",
  internalPlatform: "Internal trade platform",
  languageChanged: "Interface language changed",
} as const;

const shellTr: Record<keyof typeof shellEn, string> = {
  workspace: "Çalışma alanı",
  sessionVerified: "Oturum doğrulandı",
  systemStatus: "Sistem durumu",
  profileAccess: "Profil ve erişim",
  language: "Arayüz dili",
  english: "English",
  turkish: "Türkçe",
  openNavigation: "Menüyü aç",
  closeNavigation: "Menüyü kapat",
  mobilePrimary: "Mobil ana menü",
  platform: "Platform",
  internalPlatform: "Dış ticaret yönetim platformu",
  languageChanged: "Arayüz dili değiştirildi",
};

const en = {
  ...shellEn,
  ...commonEn,
  ...importsEn,
  ...documentsEn,
  ...authEn,
  ...tradeEn,
  ...dashboardEn,
  ...dealsEn,
} as const;
export type MessageKey = keyof typeof en;
type Dictionary = Record<MessageKey, string>;

const tr: Dictionary = {
  ...shellTr,
  ...commonTr,
  ...importsTr,
  ...documentsTr,
  ...authTr,
  ...tradeTr,
  ...dashboardTr,
  ...dealsTr,
};

const dictionaries: Record<Locale, Dictionary> = { en, tr };

export const ALL_MESSAGE_KEYS = Object.keys(en) as MessageKey[];

export function normalizeLocale(candidate: string | null | undefined): Locale {
  return candidate === "tr" ? "tr" : "en";
}

/** `{name}` placeholders are replaced from `params`; unknown placeholders stay visible. */
export function translate(
  locale: Locale,
  key: MessageKey,
  params?: Record<string, string | number>,
): string {
  const template = dictionaries[locale][key];
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in params ? String(params[name]) : match,
  );
}
