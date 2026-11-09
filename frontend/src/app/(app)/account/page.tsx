import { Building2, ShieldCheck } from "lucide-react";

import { AccountSummary } from "@/components/auth/account-summary";
import { CompanySwitcher } from "@/components/auth/company-switcher";
import { LogoutButton } from "@/components/auth/logout-button";
import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/components/ui/page-header";
import { loadSession } from "@/lib/auth/session";
import type { MessageKey } from "@/lib/i18n/messages";
import { getServerT, titleFor } from "@/lib/i18n/server";

export const dynamic = "force-dynamic";
export const generateMetadata = () => titleFor("acctPageTitle");

const SESSION_POLICY: readonly { term: MessageKey; detail: MessageKey }[] = [
  { term: "acctIdleTerm", detail: "acctIdleDetail" },
  { term: "acctAbsoluteTerm", detail: "acctAbsoluteDetail" },
  { term: "acctRevocationTerm", detail: "acctRevocationDetail" },
  { term: "acctStorageTerm", detail: "acctStorageDetail" },
];

export default async function AccountPage() {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;
  const { t } = await getServerT();

  const { session, memberships } = state.session;
  const company = session.company;

  return (
    <div className="mx-auto max-w-[1280px] space-y-5">
      <PageHeader
        eyebrow={t("acctEyebrow")}
        meta={
          <Badge variant="success" dot>
            {t("acctAuthenticated")}
          </Badge>
        }
        title={t("acctTitle")}
        description={t("acctDescription")}
        actions={<LogoutButton csrfToken={session.csrf_token} />}
      />

      <section className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <div className="panel overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-3 px-5 pt-4.5 pb-3">
            <div>
              <p className="eyebrow">{t("acctIdentity")}</p>
              <h2 className="mt-1.5 text-[14px] font-medium text-mist-100">
                {t("acctSignedInProfile")}
              </h2>
            </div>
            <ShieldCheck className="size-4 text-accent-300" aria-hidden />
          </div>
          <div className="hairline" />
          <div className="p-5">
            <AccountSummary session={state.session} />
          </div>
        </div>

        <div className="panel self-start overflow-hidden">
          <div className="flex items-start justify-between gap-3 px-5 pt-4.5 pb-3">
            <div>
              <p className="eyebrow">{t("acctMemberships")}</p>
              <h2 className="mt-1.5 text-[14px] font-medium text-mist-100">
                {t("acctCompanyAccess")}
              </h2>
            </div>
            <Badge variant="secondary">{t("acctAvailable", { count: memberships.length })}</Badge>
          </div>
          <div className="hairline" />
          <div className="p-5">
            <p className="flex items-start gap-2 text-[11px] leading-relaxed text-mist-500">
              <Building2 className="mt-[2px] size-3.5 shrink-0 text-mist-600" aria-hidden />
              {t("acctSwitchNote")}
            </p>
            <div className="mt-4">
              <CompanySwitcher
                companies={memberships}
                activeCompanyId={company?.company_id ?? null}
                csrfToken={session.csrf_token}
              />
            </div>
          </div>
        </div>
      </section>

      <section className="panel overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 px-5 pt-4.5 pb-3">
          <div>
            <p className="eyebrow">{t("acctSecurity")}</p>
            <h2 className="mt-1.5 text-[14px] font-medium text-mist-100">
              {t("acctSessionPolicy")}
            </h2>
          </div>
          <span className="text-[10.5px] text-mist-600">{t("acctEnforced")}</span>
        </div>
        <div className="hairline" />
        <dl className="grid grid-cols-1 gap-px bg-white/[0.05] sm:grid-cols-2 xl:grid-cols-4">
          {SESSION_POLICY.map((item) => (
            <div key={item.term} className="bg-ink-900/70 px-5 py-4">
              <dt className="text-[9.5px] tracking-[0.18em] text-mist-600 uppercase">
                {t(item.term)}
              </dt>
              <dd className="mt-1.5 text-[11.5px] leading-relaxed text-mist-400">
                {t(item.detail)}
              </dd>
            </div>
          ))}
        </dl>
      </section>
    </div>
  );
}
