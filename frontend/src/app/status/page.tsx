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
import {
  formatLatency,
  formatUtcTimestamp,
  stateFromResult,
  summariseDatabase,
} from "@/lib/status";

export const dynamic = "force-dynamic";
export const metadata = { title: "System status" };

/**
 * Public, read-only infrastructure status.
 *
 * Deliberately outside the authenticated shell: operators need a health view
 * even when nobody can sign in. It exposes no session, company or user data.
 */
export default async function PublicStatusPage() {
  const [live, readiness, contract] = await Promise.all([
    fetchLiveness(),
    fetchReadiness(),
    fetchContract(),
  ]);

  const database = summariseDatabase(readiness);
  const issues: { title: string; detail: string }[] = [];
  if (!live.ok) {
    issues.push({
      title: "API unreachable",
      detail: `${live.message} Start it with scripts\\dev-backend.ps1 and listen on port 8000.`,
    });
  }
  if (live.ok && !readiness.ok) {
    issues.push({
      title: "Database not ready",
      detail: `${database.detail} Start PostgreSQL (scripts\\db\\start-local-postgres.ps1) and apply migrations (scripts\\migrate.ps1).`,
    });
  }
  if (!contract.ok) {
    issues.push({
      title: "OpenAPI contract unavailable",
      detail: `${contract.message} Regenerate frontend types with scripts\\generate-api-types.ps1.`,
    });
  }

  return (
    <div className="relative min-h-screen">
      <div className="hairline-grid pointer-events-none absolute inset-0 opacity-70" aria-hidden />
      <div className="relative mx-auto max-w-[1180px] space-y-8 px-6 py-10">
        <PageHeader
          eyebrow="Platform"
          meta={
            <Badge variant="outline">
              <ShieldCheck className="size-3 text-accent-300" aria-hidden />
              Public · read only
            </Badge>
          }
          title="System status"
          description="Live connectivity between the web shell, the FastAPI service and PostgreSQL. This page requires no session and shows no user, company or business data."
          actions={
            <>
              <span className="hidden text-[10.5px] text-mist-600 sm:inline">
                Rendered {formatUtcTimestamp(new Date().toISOString())}
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

        <section className="grid gap-4 lg:grid-cols-3">
          <ProbeCard
            eyebrow="Liveness"
            title="FastAPI service"
            state={stateFromResult(live)}
            value={
              live.ok
                ? `${live.data.service} v${live.data.version} answered HTTP ${live.status}.`
                : live.message
            }
            rows={[
              { label: "Endpoint", value: "/api/v1/health/live" },
              { label: "Request ID", value: live.requestId ?? "—", mono: true },
              { label: "Latency", value: formatLatency(live.latencyMs) },
            ]}
            footer="Liveness never touches PostgreSQL."
          />
          <ProbeCard
            eyebrow="Readiness"
            title="PostgreSQL"
            state={database.state}
            value={database.detail}
            rows={[
              { label: "Server", value: database.server ?? "not reported" },
              { label: "Role", value: database.role ?? "not reported", mono: true },
              { label: "Latency", value: formatLatency(database.latencyMs) },
            ]}
            footer="Readiness uses the runtime role (no DDL, no BYPASSRLS)."
          />
          <ProbeCard
            eyebrow="Contract"
            title="Typed API contract"
            state={stateFromResult(contract)}
            value={
              contract.ok
                ? `${contract.data.operationCount} operations published by ${
                    contract.data.title ?? "the API"
                  }.`
                : contract.message
            }
            rows={[
              { label: "Document", value: "/api/v1/openapi.json", mono: true },
              { label: "Version", value: contract.ok ? (contract.data.version ?? "—") : "—" },
              { label: "Latency", value: formatLatency(contract.latencyMs) },
            ]}
            footer="Generated types are drift-checked in CI."
          />
        </section>

        <section className="panel overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-4 px-5 py-4">
            <div>
              <span className="eyebrow">Need to work?</span>
              <p className="mt-1.5 max-w-xl text-[12px] leading-relaxed text-mist-400">
                The workspace — deals, documents and settlement — requires a signed-in session
                scoped to a company membership.
              </p>
            </div>
            <Button asChild variant="outline" size="sm">
              <Link href="/login">
                Sign in
                <ArrowRight className="size-3.5" aria-hidden />
              </Link>
            </Button>
          </div>
        </section>

        <footer className="flex flex-wrap items-center gap-x-6 gap-y-2 pb-4 text-[11px] text-mist-600">
          <span className="inline-flex items-center gap-1.5">
            <Server className="size-3.5" aria-hidden />
            API {API_URLS.base}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <Database className="size-3.5" aria-hidden />
            PostgreSQL 17 · schema <span className="font-mono text-mist-500">touche</span>
          </span>
          <span className="inline-flex items-center gap-1.5">
            <FileJson className="size-3.5" aria-hidden />
            OpenAPI {API_URLS.openapi}
          </span>
        </footer>
      </div>
    </div>
  );
}
