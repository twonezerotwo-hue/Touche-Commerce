import {
  ArrowUpRight,
  CircleAlert,
  CircleCheck,
  Database,
  FileJson,
  Server,
  Waypoints,
} from "lucide-react";

import { ProbeCard } from "@/components/system-status/probe-card";
import { RefreshButton } from "@/components/system-status/refresh-button";
import { Badge } from "@/components/ui/badge";
import { fetchContract, fetchLiveness, fetchReadiness } from "@/lib/api/client";
import { API_BASE_URL, API_REQUEST_TIMEOUT_MS, API_URLS } from "@/lib/api/config";
import {
  formatLatency,
  formatUtcTimestamp,
  stateFromResult,
  summariseDatabase,
} from "@/lib/status";

// Status must never be served from a build-time cache.
export const dynamic = "force-dynamic";

const INTEGRATIONS = [
  "E-YAY",
  "Touche Finance",
  "Gmail",
  "WhatsApp Business",
  "TOUCHE ONE",
] as const;

const STAGE_1A_SCOPE = [
  "Server-side sessions with hashed tokens, rotation and idle/absolute timeouts",
  "Viewer / trader / approver / admin roles with a separate financial approval permission",
  "Companies, verified memberships and PostgreSQL RLS with transaction-scoped SET LOCAL",
  "Append-only audit log with redacted before/after snapshots",
  "Idempotency records, optimistic concurrency and login rate limiting",
] as const;

export default async function CommandCenterPage() {
  const renderedAt = new Date().toISOString();
  const [live, readiness, contract] = await Promise.all([
    fetchLiveness(),
    fetchReadiness(),
    fetchContract(),
  ]);

  const apiState = stateFromResult(live);
  const database = summariseDatabase(readiness);
  const contractState = stateFromResult(contract);

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
  const allHealthy = issues.length === 0;

  return (
    <div className="mx-auto max-w-[1320px] space-y-10">
      <header className="flex flex-wrap items-end justify-between gap-6">
        <div className="max-w-2xl">
          <div className="flex items-center gap-3">
            <span className="eyebrow">Command Center</span>
            <Badge variant="default">Stage 0</Badge>
          </div>
          <h1 className="mt-3 font-display text-[30px] leading-[1.12] tracking-tight text-mist-100 lg:text-[36px]">
            Foundation status
          </h1>
          <p className="mt-3 max-w-xl text-[13.5px] leading-relaxed text-mist-500">
            Live connectivity between the web shell, the FastAPI service and PostgreSQL. No business
            modules, AI agents or external integrations are active at this stage.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <Badge variant={allHealthy ? "success" : "warning"}>
            <span
              className={`size-1.5 rounded-full ${allHealthy ? "bg-jade-400" : "bg-amber-400"}`}
              aria-hidden
            />
            {allHealthy ? "All probes nominal" : `${issues.length} item(s) need attention`}
          </Badge>
          <RefreshButton />
        </div>
      </header>

      <section aria-labelledby="probes-heading" className="space-y-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="probes-heading" className="font-display text-lg text-mist-100">
            Live probes
          </h2>
          <p className="text-[11px] tracking-[0.04em] text-mist-600">
            Every value below came from an HTTP request made while rendering this page.
          </p>
        </div>

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <ProbeCard
            eyebrow="Web shell"
            title="Frontend"
            state="operational"
            value="This page rendered on the server for the current request."
            rows={[
              { label: "Framework", value: "Next.js 16 · App Router" },
              { label: "Rendering", value: "Server component · force-dynamic" },
              { label: "API base", value: API_BASE_URL, mono: true },
              { label: "Rendered at", value: formatUtcTimestamp(renderedAt) },
            ]}
            footer="Frontend status is proven by this render — not by a hardcoded label."
          />

          <ProbeCard
            eyebrow="Liveness"
            title="FastAPI service"
            state={apiState}
            value={
              live.ok
                ? `${live.data.service} v${live.data.version} answered HTTP ${live.status}.`
                : live.message
            }
            rows={[
              { label: "Endpoint", value: "/api/v1/health/live", mono: true },
              { label: "HTTP", value: live.status === null ? "no response" : `${live.status}` },
              { label: "Latency", value: formatLatency(live.latencyMs) },
              { label: "Request ID", value: live.requestId ?? "—", mono: true, muted: true },
            ]}
            footer={
              live.ok
                ? `Environment: ${live.data.environment} · liveness never touches PostgreSQL.`
                : `${live.code} · ${live.message}`
            }
          />

          <ProbeCard
            eyebrow="Readiness"
            title="PostgreSQL"
            state={database.state}
            value={database.detail}
            rows={[
              {
                label: "Server",
                value: database.server ? `PostgreSQL ${database.server}` : "not reported",
              },
              { label: "Runtime role", value: database.role ?? "—", mono: true },
              { label: "Probe latency", value: formatLatency(database.latencyMs) },
              {
                label: "HTTP",
                value: readiness.status === null ? "no response" : `${readiness.status}`,
              },
            ]}
            footer={
              database.errorCode
                ? `Error code: ${database.errorCode} · readiness uses the least-privilege runtime role.`
                : "Readiness verifies the runtime role can query the database (no DDL rights)."
            }
          />

          <ProbeCard
            eyebrow="Contract"
            title="OpenAPI v1"
            state={contractState}
            value={
              contract.ok
                ? `${contract.data.operationCount} operations exposed by the v1 document.`
                : contract.message
            }
            rows={[
              { label: "Namespace", value: "/api/v1", mono: true },
              {
                label: "Document",
                value: contract.ok
                  ? `${contract.data.title ?? "TOUCHE API"} v${contract.data.version ?? "—"}`
                  : "unavailable",
              },
              { label: "Types", value: "OpenAPI → TypeScript", mono: true },
              { label: "Docs", value: "/docs", mono: true },
            ]}
            footer={
              contract.ok
                ? "Frontend DTOs are generated from this document (openapi-typescript)."
                : `${contract.code} · ${contract.message}`
            }
          />
        </div>
      </section>

      <section className="grid gap-4 xl:grid-cols-[1.6fr_1fr]">
        <div className="panel rounded-xl p-6">
          <div className="flex items-center gap-2">
            <Waypoints className="size-4 text-gold-400" aria-hidden />
            <h2 className="font-display text-lg text-mist-100">Connection detail</h2>
          </div>

          <dl className="mt-5 grid gap-4 sm:grid-cols-2">
            <Detail label="API base URL" value={API_BASE_URL} mono />
            <Detail label="Request timeout" value={`${API_REQUEST_TIMEOUT_MS} ms`} />
            <Detail label="Probe namespace" value="/api/v1" mono />
            <Detail label="Checked at" value={formatUtcTimestamp(renderedAt)} />
          </dl>

          <div className="rule my-5" />

          {allHealthy ? (
            <div className="flex items-start gap-3">
              <CircleCheck className="mt-0.5 size-4 shrink-0 text-jade-400" aria-hidden />
              <div>
                <p className="text-[13px] text-mist-200">All Stage 0 probes responded.</p>
                <p className="mt-1 text-[12px] leading-relaxed text-mist-500">
                  API liveness, database readiness and the OpenAPI document are reachable from this
                  server render. Authentication and business modules are intentionally absent.
                </p>
              </div>
            </div>
          ) : (
            <ul className="space-y-4">
              {issues.map((issue) => (
                <li key={issue.title} className="flex items-start gap-3">
                  <CircleAlert className="mt-0.5 size-4 shrink-0 text-amber-400" aria-hidden />
                  <div>
                    <p className="text-[13px] text-mist-200">{issue.title}</p>
                    <p className="mt-1 break-words text-[12px] leading-relaxed text-mist-500">
                      {issue.detail}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="panel rounded-xl p-6">
          <div className="flex items-center gap-2">
            <FileJson className="size-4 text-gold-400" aria-hidden />
            <h2 className="font-display text-lg text-mist-100">Platform boundaries</h2>
          </div>
          <p className="mt-2 text-[12.5px] leading-relaxed text-mist-500">
            Stage 0 ships infrastructure only. These integrations are designed for but not connected
            today.
          </p>

          <ul className="mt-4 space-y-2">
            {INTEGRATIONS.map((name) => (
              <li
                key={name}
                className="flex items-center justify-between rounded-md border border-white/[0.05] bg-white/[0.015] px-3 py-2"
              >
                <span className="text-[12.5px] text-mist-300">{name}</span>
                <span className="text-[9.5px] uppercase tracking-[0.14em] text-mist-600">
                  not connected
                </span>
              </li>
            ))}
          </ul>

          <div className="rule my-5" />
          <p className="text-[11px] leading-relaxed text-mist-600">
            No KPIs, deals, quotations or financial figures are displayed because no business data
            exists yet. Placeholder modules in the navigation are labelled with their stage.
          </p>
        </div>
      </section>

      <section className="panel rounded-xl p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <span className="eyebrow">Next milestone</span>
            <h2 className="mt-2 font-display text-lg text-mist-100">
              Stage 1A · identity, sessions &amp; tenancy
            </h2>
          </div>
          <Badge variant="warning">Not started</Badge>
        </div>
        <ul className="mt-5 grid gap-2.5 sm:grid-cols-2">
          {STAGE_1A_SCOPE.map((item) => (
            <li key={item} className="flex gap-2.5 text-[12.5px] leading-relaxed text-mist-400">
              <span className="mt-[7px] size-1 shrink-0 rounded-full bg-gold-400/70" aria-hidden />
              <span>{item}</span>
            </li>
          ))}
        </ul>
      </section>

      <footer className="flex flex-wrap items-center gap-x-6 gap-y-2 pb-2 text-[11px] text-mist-600">
        <span className="inline-flex items-center gap-1.5">
          <Server className="size-3.5" aria-hidden />
          API {API_URLS.base}
        </span>
        <span className="inline-flex items-center gap-1.5">
          <Database className="size-3.5" aria-hidden />
          PostgreSQL 17 · schema <span className="font-mono text-mist-500">touche</span>
        </span>
        <span className="inline-flex items-center gap-1.5">
          <ArrowUpRight className="size-3.5" aria-hidden />
          Docs: ARCHITECTURE · API_CONTRACTS · ROADMAP · PROGRESS · DECISIONS
        </span>
      </footer>
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
