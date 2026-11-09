import type { Metadata } from "next";

import { LocaleProvider } from "@/lib/i18n/locale-provider";
import { getServerLocale, getServerT } from "@/lib/i18n/server";

import "./globals.css";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await getServerT();
  return {
    title: {
      default: t("metaDefaultTitle"),
      template: "%s · TOUCHE COMMERCE",
    },
    description: t("metaDescription"),
    applicationName: "TOUCHE COMMERCE",
    robots: { index: false, follow: false },
  };
}

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  // The language is a cookie, so the very first byte is already in the chosen language.
  const locale = await getServerLocale();
  return (
    <html lang={locale} className="dark">
      <body className="app-canvas min-h-screen">
        <LocaleProvider initialLocale={locale}>{children}</LocaleProvider>
      </body>
    </html>
  );
}
