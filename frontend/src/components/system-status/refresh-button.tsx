"use client";

import { useRouter } from "next/navigation";
import { useTransition } from "react";
import { RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useLocale } from "@/lib/i18n/locale-provider";

export function RefreshButton() {
  const router = useRouter();
  const { t } = useLocale();
  const [isPending, startTransition] = useTransition();

  return (
    <Button
      variant="outline"
      size="sm"
      disabled={isPending}
      onClick={() => {
        startTransition(() => router.refresh());
      }}
    >
      <RefreshCw className={isPending ? "size-3.5 animate-spin" : "size-3.5"} aria-hidden />
      {isPending ? t("stRechecking") : t("stRecheck")}
    </Button>
  );
}
