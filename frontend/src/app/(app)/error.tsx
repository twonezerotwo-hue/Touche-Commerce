"use client";

import Link from "next/link";
import { TriangleAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useLocale } from "@/lib/i18n/locale-provider";

/**
 * A screen that failed while rendering. The shell around it stays; the person gets words in their
 * own language and a way to try again. The error text itself is never shown: a server error is
 * deliberately generic and could carry detail that does not belong on screen.
 */
export default function AppError({ error, retry }: { error: unknown; retry: () => void }) {
  const { t } = useLocale();
  const rawDigest = error instanceof Error ? (error as Error & { digest?: unknown }).digest : null;
  const digest = typeof rawDigest === "string" ? rawDigest : null;

  return (
    <div
      role="alert"
      className="mx-auto flex min-h-[50vh] max-w-lg flex-col items-center justify-center text-center"
    >
      <span className="flex size-12 items-center justify-center rounded-full border border-crimson-400/30 bg-crimson-400/[0.08]">
        <TriangleAlert className="size-5 text-crimson-400" aria-hidden />
      </span>
      <h1 className="mt-4 font-display text-2xl tracking-tight text-mist-100">{t("errTitle")}</h1>
      <p className="mt-2 text-[13px] leading-relaxed text-mist-500">{t("errBody")}</p>
      {digest ? (
        <p className="mt-2 font-mono text-[11px] text-mist-600">{t("errReference", { digest })}</p>
      ) : null}
      <div className="mt-6 flex items-center gap-3">
        <Button type="button" variant="outline" onClick={() => retry()}>
          {t("errRetry")}
        </Button>
        <Button asChild variant="ghost">
          <Link href="/">{t("errHome")}</Link>
        </Button>
      </div>
    </div>
  );
}
