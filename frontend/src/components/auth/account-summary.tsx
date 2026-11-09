"use client";

import { KeyRound, MapPin, ShieldCheck } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { AuthSession } from "@/lib/auth/types";
import { useLocale } from "@/lib/i18n/locale-provider";
import { recordStatusLabel, roleLabel } from "@/lib/i18n/value-labels";
import { formatUtcTimestamp } from "@/lib/status";

export function AccountSummary({ session }: { session: AuthSession }) {
  const { t, locale } = useLocale();
  const { user } = session;
  const view = session.session;
  const company = view.company;

  return (
    <div className="space-y-5">
      <dl className="grid gap-4 sm:grid-cols-2">
        <Detail label={t("sumName")} value={user.display_name} />
        <Detail label={t("sumEmail")} value={user.email} mono />
        <Detail
          label={t("sumStatus")}
          value={locale === "tr" ? recordStatusLabel(t, user.status) : user.status}
        />
        <Detail
          label={t("sumRole")}
          value={company ? roleLabel(t, company.role) : t("sumNoCompany")}
        />
        <Detail
          label={t("sumActiveCompany")}
          value={company ? `${company.name} · ${company.country}` : t("sumNotSelected")}
        />
        <Detail label={t("sumStarted")} value={formatUtcTimestamp(view.created_at)} />
        <Detail label={t("sumLastActivity")} value={formatUtcTimestamp(view.last_activity_at)} />
        <Detail label={t("sumExpiresAbsolute")} value={formatUtcTimestamp(view.expires_at)} />
        <Detail label={t("sumExpiresIdle")} value={formatUtcTimestamp(view.idle_expires_at)} />
        <Detail label={t("sumSessionId")} value={view.session_id} mono />
      </dl>

      <div className="rule" />

      <div className="space-y-2">
        <p className="flex items-center gap-1.5 text-[10.5px] uppercase tracking-[0.16em] text-mist-600">
          <ShieldCheck className="size-3.5 text-accent-400" aria-hidden />
          {t("sumPermissions")}
        </p>
        {company && company.permissions.length > 0 ? (
          <ul className="flex flex-wrap gap-1.5">
            {company.permissions.map((permission) => (
              <li key={permission}>
                <Badge variant="secondary" className="font-mono text-[10.5px]">
                  <KeyRound className="size-2.5" aria-hidden />
                  {permission}
                </Badge>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-[12px] text-mist-500">{t("sumNoPermissions")}</p>
        )}
      </div>

      {view.ip_address || view.user_agent ? (
        <>
          <div className="rule" />
          <p className="flex items-start gap-1.5 text-[11px] leading-relaxed text-mist-600">
            <MapPin className="mt-[2px] size-3.5 shrink-0" aria-hidden />
            <span>
              {t("sumOrigin", {
                address: view.ip_address ?? t("sumUnknownAddress"),
                agent: view.user_agent ? ` · ${view.user_agent}` : "",
              })}
            </span>
          </p>
        </>
      ) : null}
    </div>
  );
}

function Detail({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <dt className="text-[10px] uppercase tracking-[0.16em] text-mist-600">{label}</dt>
      <dd
        className={
          mono
            ? "mt-1 break-all font-mono text-[11.5px] text-mist-200"
            : "mt-1 text-[12.5px] text-mist-200"
        }
      >
        {value}
      </dd>
    </div>
  );
}
