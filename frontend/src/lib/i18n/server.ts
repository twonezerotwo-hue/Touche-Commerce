import { cookies } from "next/headers";

import { LOCALE_COOKIE } from "./locale-cookie";
import { normalizeLocale, translate, type Locale, type MessageKey } from "./messages";

/** The language chosen in this browser (English until the person picks Turkish). */
export async function getServerLocale(): Promise<Locale> {
  return normalizeLocale((await cookies()).get(LOCALE_COOKIE)?.value);
}

export interface ServerTranslator {
  locale: Locale;
  t: (key: MessageKey, params?: Record<string, string | number>) => string;
}

/** For server components: `const { t } = await getServerT();` */
export async function getServerT(): Promise<ServerTranslator> {
  const locale = await getServerLocale();
  return { locale, t: (key, params) => translate(locale, key, params) };
}
