"use client";

import Link from "next/link";
import { ServerCrash } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useLocale } from "@/lib/i18n/locale-provider";

/**
 * Rendered when the API cannot be reached while resolving the session. The UI
 * never guesses whether the visitor is signed in.
 */
export function SessionUnavailable({ message }: { message: string }) {
  const { t } = useLocale();
  const [before, after] = t("suHint", { command: "|" }).split("|");
  return (
    <div className="mx-auto flex min-h-[60vh] max-w-lg flex-col items-center justify-center text-center">
      <span className="flex size-12 items-center justify-center rounded-full border border-crimson-400/30 bg-crimson-400/[0.08]">
        <ServerCrash className="size-5 text-crimson-400" aria-hidden />
      </span>
      <Badge variant="danger" className="mt-4">
        {t("suBadge")}
      </Badge>
      <h1 className="mt-3 font-display text-2xl tracking-tight text-mist-100">{t("suTitle")}</h1>
      <p className="mt-2 text-[13px] leading-relaxed text-mist-500">{message}</p>
      <p className="mt-1 text-[12px] leading-relaxed text-mist-600">
        {before}
        <span className="font-mono text-mist-400">scripts\dev-backend.ps1</span>
        {after}
      </p>
      <div className="mt-6 flex items-center gap-3">
        <Button asChild variant="outline">
          <Link href="/login">{t("suBack")}</Link>
        </Button>
        <Button asChild variant="ghost">
          <Link href="/status">{t("suStatus")}</Link>
        </Button>
      </div>
    </div>
  );
}
