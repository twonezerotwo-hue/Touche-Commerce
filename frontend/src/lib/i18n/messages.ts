/** Stage 12A: type-safe bilingual shell vocabulary. Trade records are NOT translated. */

export const SUPPORTED_LOCALES = ["en", "tr"] as const;
export type Locale = (typeof SUPPORTED_LOCALES)[number];

const en = {
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

export type MessageKey = keyof typeof en;
type Dictionary = Record<MessageKey, string>;

const tr: Dictionary = {
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

const dictionaries: Record<Locale, Dictionary> = { en, tr };

export function normalizeLocale(candidate: string | null | undefined): Locale {
  return candidate === "tr" ? "tr" : "en";
}

export function translate(locale: Locale, key: MessageKey): string {
  return dictionaries[locale][key];
}
