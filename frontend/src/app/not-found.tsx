import Link from "next/link";
import { Compass } from "lucide-react";

import { Button } from "@/components/ui/button";
import { getServerT, titleFor } from "@/lib/i18n/server";

export const generateMetadata = () => titleFor("nfTitle");

/** A page that does not exist, in the language chosen in this browser. */
export default async function NotFound() {
  const { t } = await getServerT();
  return (
    <main className="mx-auto flex min-h-[70vh] max-w-lg flex-col items-center justify-center px-6 text-center">
      <span className="flex size-12 items-center justify-center rounded-full border border-white/10 bg-white/[0.03]">
        <Compass className="size-5 text-accent-300" aria-hidden />
      </span>
      <p className="mt-4 font-mono text-[11px] tracking-[0.3em] text-mist-600">404</p>
      <h1 className="mt-2 font-display text-2xl tracking-tight text-mist-100">{t("nfTitle")}</h1>
      <p className="mt-2 text-[13px] leading-relaxed text-mist-500">{t("nfBody")}</p>
      <Button asChild variant="outline" className="mt-6">
        <Link href="/">{t("nfBack")}</Link>
      </Button>
    </main>
  );
}
