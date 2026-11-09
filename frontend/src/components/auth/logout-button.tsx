"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Loader2, LogOut } from "lucide-react";

import { Button } from "@/components/ui/button";
import { logout } from "@/lib/auth/client";
import { useLocale } from "@/lib/i18n/locale-provider";
import { cn } from "@/lib/utils";

export function LogoutButton({
  csrfToken,
  className,
  label,
}: {
  csrfToken: string;
  className?: string;
  label?: string;
}) {
  const router = useRouter();
  const { t } = useLocale();
  const text = label ?? t("logoutLabel");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onLogout(): Promise<void> {
    setError(null);
    setPending(true);
    const result = await logout(csrfToken);
    setPending(false);

    if (!result.ok) {
      setError(result.message);
      return;
    }
    router.replace("/login");
    router.refresh();
  }

  return (
    <div className={cn("flex flex-col items-end gap-1", className)}>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={onLogout}
        disabled={pending}
        aria-label={text}
      >
        {pending ? (
          <Loader2 className="size-3.5 animate-spin" aria-hidden />
        ) : (
          <LogOut className="size-3.5" aria-hidden />
        )}
        {pending ? t("logoutPending") : text}
      </Button>
      {error ? (
        <span role="alert" className="text-[10.5px] text-crimson-400">
          {error}
        </span>
      ) : null}
    </div>
  );
}
