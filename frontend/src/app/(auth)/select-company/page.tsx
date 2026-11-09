import { redirect } from "next/navigation";
import { Building2 } from "lucide-react";

import { CompanySwitcher } from "@/components/auth/company-switcher";
import { LogoutButton } from "@/components/auth/logout-button";
import { SessionUnavailable } from "@/components/auth/session-unavailable";
import { Badge } from "@/components/ui/badge";
import { resolveRoute } from "@/lib/auth/guard";
import { loadSession } from "@/lib/auth/session";
import { getServerT, titleFor } from "@/lib/i18n/server";

export const dynamic = "force-dynamic";
export const generateMetadata = () => titleFor("selPageTitle");

export default async function SelectCompanyPage() {
  const state = await loadSession();
  const decision = resolveRoute(state, "/select-company");
  if (decision.redirectTo) redirect(decision.redirectTo);

  if (state.status === "unavailable") {
    return <SessionUnavailable message={state.message} />;
  }
  if (state.status !== "authenticated") return null;
  const { t } = await getServerT();

  const { user, session, memberships } = state.session;

  return (
    <div className="panel rounded-xl p-7">
      <div className="flex items-start justify-between gap-3">
        <div>
          <span className="eyebrow">{t("selEyebrow")}</span>
          <h2 className="mt-2 font-display text-[25px] leading-tight tracking-tight text-mist-100">
            {t("selTitle")}
          </h2>
        </div>
        <Badge variant="secondary">
          <Building2 className="size-3" aria-hidden />
          {t("acctAvailable", { count: memberships.length })}
        </Badge>
      </div>

      <p className="mt-2 text-[12.5px] leading-relaxed text-mist-500">
        {t("selSignedInAs")} <span className="text-mist-200">{user.display_name}</span> (
        {user.email}). {t("selIntro")}
      </p>

      <div className="rule my-6" />

      <CompanySwitcher
        companies={memberships}
        activeCompanyId={session.company?.company_id ?? null}
        csrfToken={session.csrf_token}
      />

      <div className="rule my-6" />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-[60%] text-[11px] leading-relaxed text-mist-600">
          {t("selRevocation")}
        </p>
        <LogoutButton csrfToken={session.csrf_token} />
      </div>
    </div>
  );
}
