"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Building2, Check, Loader2 } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { switchCompany } from "@/lib/auth/client";
import type { CompanyAccess } from "@/lib/auth/types";
import { cn } from "@/lib/utils";

const ROLE_LABEL: Record<string, string> = {
  viewer: "Viewer",
  trader: "Trader",
  approver: "Approver",
  admin: "Administrator",
};

export function CompanySwitcher({
  companies,
  activeCompanyId,
  csrfToken,
  onSelected,
}: {
  companies: readonly CompanyAccess[];
  activeCompanyId: string | null;
  csrfToken: string;
  /** Called after a successful switch; defaults to a server refresh. */
  onSelected?: () => void;
}) {
  const router = useRouter();
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function select(companyId: string): Promise<void> {
    if (companyId === activeCompanyId || pendingId) return;
    setError(null);
    setPendingId(companyId);

    const result = await switchCompany(companyId, csrfToken);
    setPendingId(null);

    if (!result.ok) {
      setError(result.message);
      return;
    }
    if (onSelected) onSelected();
    else router.refresh();
  }

  if (companies.length === 0) {
    return (
      <Alert variant="warning" title="No company access">
        Your account has no active company membership. Ask an administrator to grant access.
      </Alert>
    );
  }

  return (
    <div className="space-y-3">
      {error ? <Alert variant="danger">{error}</Alert> : null}
      <ul className="space-y-2">
        {companies.map((company) => {
          const isActive = company.company_id === activeCompanyId;
          const isPending = pendingId === company.company_id;
          return (
            <li key={company.company_id}>
              <button
                type="button"
                onClick={() => select(company.company_id)}
                disabled={isActive || pendingId !== null}
                aria-pressed={isActive}
                className={cn(
                  "flex w-full items-center gap-3 rounded-lg border px-4 py-3 text-left transition-colors",
                  isActive
                    ? "border-accent-400/40 bg-accent-400/[0.06]"
                    : "border-white/[0.07] bg-white/[0.015] hover:border-accent-400/30 hover:bg-white/[0.035]",
                  pendingId !== null && !isPending && "opacity-60",
                )}
              >
                <span
                  className={cn(
                    "flex size-9 shrink-0 items-center justify-center rounded-md border",
                    isActive
                      ? "border-accent-400/40 text-accent-300"
                      : "border-white/10 text-mist-500",
                  )}
                >
                  {isPending ? (
                    <Loader2 className="size-4 animate-spin" aria-hidden />
                  ) : (
                    <Building2 className="size-4" aria-hidden />
                  )}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13.5px] text-mist-100">{company.name}</span>
                  <span className="mt-0.5 block text-[11px] text-mist-600">
                    {company.country} · {company.default_currency} ·{" "}
                    {ROLE_LABEL[company.role] ?? company.role}
                  </span>
                </span>
                {isActive ? (
                  <Badge variant="default">
                    <Check className="size-3" aria-hidden />
                    Current
                  </Badge>
                ) : (
                  <span className="text-[10px] uppercase tracking-[0.14em] text-mist-600">
                    {isPending ? "Switching" : "Select"}
                  </span>
                )}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
