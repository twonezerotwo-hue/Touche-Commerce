import Link from "next/link";
import { ArrowRight, CircleAlert, Database, FileJson, Server, ShieldCheck } from "lucide-react";

import { ProbeCard } from "@/components/system-status/probe-card";
import { RefreshButton } from "@/components/system-status/refresh-button";
import { Badge } from "@/components/ui/badge";
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
        <header className="flex flex-wrap items-end justify-between gap-6">
          <div className="max-w-2xl">
            <div className="flex items-center gap-3">
              <span className="eyebrow">Platform</span>
              <Badge variant="outline">
                <ShieldCheck className="size-3 text-gold-400" aria-hidden />
                Public · read only
              </Badge>
            </div>
            <h1 className="mt-3 font-display text-[30px] leading-[1.12] tracking-tight text-mist-100">
              System status
            </h1>
            <p className="mt-3 max-w-xl text-[13px] leading-relaxed text-mist-500">
              Live connectivity between the web shell, the FastAPI service and PostgreSQL. This page
              requires no session and shows no user, company or business data.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-[11px] text-mist-600">
              Rendered {formatUtcTimestamp(new Date().toISOString())}
            </span>
            <RefreshButton />
          </div>
        </header>

        {issues.length > 0 ? (
          <section className="space-y-2">
            {issues.map((issue) => (
              <div
                key={issue.title}
                className="panel flex items-start gap-3 rounded-lg border-amber-400/20 p-4"
              >
                <CircleAlert className="mt-[2px] size-4 shrink-0 text-amber-400" aria-hidden />
                <div>
                  <p className="text-[13px] text-mist-100">{issue.title}</p>
                  <p className="mt-0.5 text-[12px] leading-relaxed text-mist-500">{issue.detail}</p>
                </div>
              </div>
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

        <section className="panel rounded-xl p-6">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <span className="eyebrow">Need to work?</span>
              <p className="mt-2 max-w-xl text-[12.5px] leading-relaxed text-mist-400">
                The workspace — deals, documents and settlement — requires a signed-in session
                scoped to a company membership.
              </p>
            </div>
            <Link
              href="/login"
              className="inline-flex items-center gap-1.5 rounded-md border border-white/10 px-3 py-2 text-[12px] text-mist-200 transition-colors hover:border-gold-400/40 hover:text-mist-100"
            >
              Sign in
              <ArrowRight className="size-3.5" aria-hidden />
            </Link>
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
