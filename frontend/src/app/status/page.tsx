import Link from "next/link";
import { ArrowRight, Database, FileJson, Server, ShieldCheck } from "lucide-react";

import { ProbeCard } from "@/components/system-status/probe-card";
import { RefreshButton } from "@/components/system-status/refresh-button";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { fetchContract, fetchLiveness, fetchReadiness } from "@/lib/api/client";
import { API_URLS } from "@/lib/api/config";
import { getServerT, titleFor } from "@/lib/i18n/server";
import {
  NO_DATABASE_CHECK_DETAIL,
  formatLatency,
  formatUtcTimestamp,
  stateFromResult,
  summariseDatabase,
} from "@/lib/status";

export const dynamic = "force-dynamic";
export const generateMetadata = () => titleFor("stPageTitle");

/**
 * Public, read-only infrastructure status.
 *
 * Deliberately outside the authenticated shell: operators need a health view
 * even when nobody can sign in. It exposes no session, company or user data.
 */
export default async function PublicStatusPage() {
  const { t, locale } = await getServerT();
  const [live, readiness, contract] = await Promise.all([
    fetchLiveness(locale),
    fetchReadiness(locale),
    fetchContract(locale),
  ]);

  const database = summariseDatabase(readiness);
  // A message the API wrote stays as received; the one sentence this app wrote is translated.
  const databaseDetail =
    database.detail === NO_DATABASE_CHECK_DETAIL ? t("stNoDbCheck") : database.detail;
  const notReported = t("stNotReported");
  const issues: { title: string; detail: string }[] = [];
  if (!live.ok) {
    issues.push({
      title: t("stApiDownTitle"),
      detail: `${live.message} ${t("stApiDownHint")}`,
    });
  }
  if (live.ok && !readiness.ok) {
    issues.push({
      title: t("stDbDownTitle"),
      detail: `${databaseDetail} ${t("stDbDownHint")}`,
    });
  }
  if (!contract.ok) {
    issues.push({
      title: t("stContractDownTitle"),
      detail: `${contract.message} ${t("stContractDownHint")}`,
    });
  }

  return (
    <div className="relative min-h-screen">
      <div className="hairline-grid pointer-events-none absolute inset-0 opacity-70" aria-hidden />
      <main className="relative mx-auto max-w-[1180px] space-y-8 px-6 py-10">
        <PageHeader
          eyebrow={t("stEyebrow")}
          meta={
            <Badge variant="outline">
              <ShieldCheck className="size-3 text-accent-300" aria-hidden />
              {t("stBadge")}
            </Badge>
          }
          title={t("stTitle")}
          description={t("stDescription")}
          actions={
            <>
              <span className="hidden text-[10.5px] text-mist-600 sm:inline">
                {t("stRendered", { time: formatUtcTimestamp(new Date().toISOString()) })}
              </span>
              <RefreshButton />
            </>
          }
        />

        {issues.length > 0 ? (
          <section className="space-y-2">
            {issues.map((issue) => (
              <Alert key={issue.title} variant="warning" title={issue.title}>
                {issue.detail}
              </Alert>
            ))}
          </section>
        ) : null}

        <section className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <ProbeCard
            eyebrow={t("stLivenessEyebrow")}
            title={t("stLivenessTitle")}
            state={stateFromResult(live)}
            value={
              live.ok
                ? t("stLivenessAnswered", {
                    service: live.data.service,
                    version: live.data.version,
                    status: live.status,
                  })
                : live.message
            }
            rows={[
              { label: t("stRowEndpoint"), value: "/api/v1/health/live" },
              { label: t("stRowRequestId"), value: live.requestId ?? "—", mono: true },
              { label: t("stRowLatency"), value: formatLatency(live.latencyMs) },
            ]}
            footer={t("stLivenessFooter")}
          />
          <ProbeCard
            eyebrow={t("stReadinessEyebrow")}
            title={t("stReadinessTitle")}
            state={database.state}
            value={databaseDetail}
            rows={[
              { label: t("stRowServer"), value: database.server ?? notReported },
              { label: t("stRowRole"), value: database.role ?? notReported, mono: true },
              { label: t("stRowLatency"), value: formatLatency(database.latencyMs) },
            ]}
            footer={t("stReadinessFooter")}
          />
          <ProbeCard
            eyebrow={t("stContractEyebrow")}
            title={t("stContractTitle")}
            state={stateFromResult(contract)}
            value={
              contract.ok
                ? t("stContractPublished", {
                    count: contract.data.operationCount,
                    title: contract.data.title ?? t("stContractTheApi"),
                  })
                : contract.message
            }
            rows={[
              { label: t("stRowDocument"), value: "/api/v1/openapi.json", mono: true },
              {
                label: t("stRowVersion"),
                value: contract.ok ? (contract.data.version ?? "—") : "—",
              },
              { label: t("stRowLatency"), value: formatLatency(contract.latencyMs) },
            ]}
            footer={t("stContractFooter")}
          />
        </section>

        <section className="panel overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-4 px-5 py-4">
            <div>
              <span className="eyebrow">{t("stNeedTitle")}</span>
              <p className="mt-1.5 max-w-xl text-[12px] leading-relaxed text-mist-400">
                {t("stNeedBody")}
              </p>
            </div>
            <Button asChild variant="outline" size="sm">
              <Link href="/login">
                {t("stSignIn")}
                <ArrowRight className="size-3.5" aria-hidden />
              </Link>
            </Button>
          </div>
        </section>

        <footer className="flex flex-wrap items-center gap-x-6 gap-y-2 pb-4 text-[11px] text-mist-600">
          <span className="inline-flex items-center gap-1.5">
            <Server className="size-3.5" aria-hidden />
            {t("stFooterApi", { url: API_URLS.base })}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <Database className="size-3.5" aria-hidden />
            PostgreSQL 17 · {t("stFooterSchema")}{" "}
            <span className="font-mono text-mist-500">touche</span>
          </span>
          <span className="inline-flex items-center gap-1.5">
            <FileJson className="size-3.5" aria-hidden />
            {t("stFooterOpenApi", { url: API_URLS.openapi })}
          </span>
        </footer>
      </main>
    </div>
  );
}
