"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Loader2, LogOut } from "lucide-react";

import { Button } from "@/components/ui/button";
import { logout } from "@/lib/auth/client";
import { cn } from "@/lib/utils";

export function LogoutButton({
  csrfToken,
  className,
  label = "Sign out",
}: {
  csrfToken: string;
  className?: string;
  label?: string;
}) {
  const router = useRouter();
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
        aria-label={label}
      >
        {pending ? (
          <Loader2 className="size-3.5 animate-spin" aria-hidden />
        ) : (
          <LogOut className="size-3.5" aria-hidden />
        )}
        {pending ? "Signing out…" : label}
      </Button>
      {error ? (
        <span role="alert" className="text-[10.5px] text-crimson-400">
          {error}
        </span>
      ) : null}
    </div>
  );
}
