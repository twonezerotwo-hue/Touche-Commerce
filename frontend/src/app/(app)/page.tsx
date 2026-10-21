import Link from "next/link";
import {
  ArrowUpRight,
  Building2,
  CircleAlert,
  Database,
  Layers,
  Server,
  ShieldCheck,
  UserRound,
} from "lucide-react";

import { CompanySwitcher } from "@/components/auth/company-switcher";
import { ProbeCard } from "@/components/system-status/probe-card";
import { RefreshButton } from "@/components/system-status/refresh-button";
import { Badge } from "@/components/ui/badge";
import { fetchContract, fetchLiveness, fetchReadiness } from "@/lib/api/client";
import { API_URLS } from "@/lib/api/config";
import { loadSession } from "@/lib/auth/session";
import {
  formatLatency,
  formatUtcTimestamp,
  stateFromResult,
  summariseDatabase,
} from "@/lib/status";

export const dynamic = "force-dynamic";
export const metadata = { title: "Command Center" };

const ROLE_LABEL: Record<string, string> = {
  viewer: "Viewer",
  trader: "Trader",
  approver: "Approver",
  admin: "Administrator",
};

const STAGE_1A_SCOPE = [
  "Server-side sessions: hashed tokens, rotation, 30 min idle / 12 h absolute expiry",
  "Argon2id password verification with account and source rate limiting",
  "Company membership with viewer / trader / approver / admin roles",
  "PostgreSQL row level security with transaction-scoped tenant context",
  "Append-only audit trail and CSRF + Origin validation on every mutation",
] as const;

export default async function CommandCenterPage() {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;

  const { user, session, memberships } = state.session;
  const company = session.company;

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
  const allHealthy = issues.length === 0;

  return (
    <div className="mx-auto max-w-[1320px] space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-6">
        <div className="max-w-2xl">
          <div className="flex items-center gap-3">
            <span className="eyebrow">Command Center</span>
            <Badge variant="default">Stage 1A</Badge>
          </div>
          <h1 className="mt-3 font-display text-[30px] leading-[1.12] tracking-tight text-mist-100 lg:text-[36px]">
            {greeting()}, {user.display_name.split(" ")[0]}
          </h1>
          <p className="mt-3 max-w-xl text-[13.5px] leading-relaxed text-mist-500">
            Your session, membership and the live health of the platform. Business modules are not
            active at this stage — nothing here represents trade, finance or customer data.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <Badge variant={allHealthy ? "success" : "warning"}>
            <span
              className={`size-1.5 rounded-full ${allHealthy ? "bg-jade-400" : "bg-amber-400"}`}
              aria-hidden
            />
            {allHealthy ? "All probes nominal" : `${issues.length} issue(s) detected`}
          </Badge>
          <RefreshButton />
        </div>
      </header>

      <section className="grid gap-4 lg:grid-cols-2">
        <div className="panel rounded-xl p-6">
          <div className="flex items-start justify-between gap-3">
            <div>
              <span className="eyebrow">Active company</span>
              <h2 className="mt-2 flex items-center gap-2 font-display text-lg text-mist-100">
                <Building2 className="size-4 text-gold-400" aria-hidden />
                {company?.name ?? "Not selected"}
              </h2>
              <p className="mt-1 text-[12px] text-mist-500">
                {company
                  ? `${company.country} · ${company.default_currency} · ${
                      ROLE_LABEL[company.role] ?? company.role
                    }`
                  : "Select a company to scope your session."}
              </p>
            </div>
            <Badge variant="secondary">{memberships.length} membership(s)</Badge>
          </div>

          <div className="rule my-5" />

          <CompanySwitcher
            companies={memberships}
            activeCompanyId={company?.company_id ?? null}
            csrfToken={session.csrf_token}
          />

          <div className="mt-4 flex flex-wrap gap-1.5">
            {company?.permissions.map((permission) => (
              <Badge key={permission} variant="outline" className="font-mono text-[10px]">
                {permission}
              </Badge>
            ))}
          </div>
        </div>

        <div className="panel rounded-xl p-6">
          <div className="flex items-start justify-between gap-3">
            <div>
              <span className="eyebrow">Signed in as</span>
              <h2 className="mt-2 flex items-center gap-2 font-display text-lg text-mist-100">
                <UserRound className="size-4 text-gold-400" aria-hidden />
                {user.display_name}
              </h2>
              <p className="mt-1 break-all text-[12px] text-mist-500">{user.email}</p>
            </div>
            <Badge variant="success">
              <ShieldCheck className="size-3" aria-hidden />
              {user.status}
            </Badge>
          </div>

          <div className="rule my-5" />

          <dl className="space-y-3">
            <Row label="Session started" value={formatUtcTimestamp(session.created_at)} />
            <Row label="Last activity" value={formatUtcTimestamp(session.last_activity_at)} />
            <Row label="Idle expiry" value={formatUtcTimestamp(session.idle_expires_at)} />
            <Row label="Absolute expiry" value={formatUtcTimestamp(session.expires_at)} />
            <Row label="Session id" value={session.session_id} mono />
          </dl>

          <div className="rule my-5" />
          <Link
            href="/account"
            className="inline-flex items-center gap-1.5 text-[12px] text-gold-300 transition-colors hover:text-gold-200"
          >
            Account &amp; permissions
            <ArrowUpRight className="size-3.5" aria-hidden />
          </Link>
        </div>
      </section>

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
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <span className="eyebrow">Delivered in this stage</span>
            <h2 className="mt-2 flex items-center gap-2 font-display text-lg text-mist-100">
              <Layers className="size-4 text-gold-400" aria-hidden />
              Stage 1A · identity, sessions &amp; tenancy
            </h2>
          </div>
          <Badge variant="success">Implemented</Badge>
        </div>
        <ul className="mt-5 grid gap-2.5 sm:grid-cols-2">
          {STAGE_1A_SCOPE.map((item) => (
            <li key={item} className="flex gap-2.5 text-[12.5px] leading-relaxed text-mist-400">
              <span className="mt-[7px] size-1 shrink-0 rounded-full bg-jade-400/80" aria-hidden />
              <span>{item}</span>
            </li>
          ))}
        </ul>
        <div className="rule my-5" />
        <p className="text-[11px] leading-relaxed text-mist-600">
          Next milestone: Stage 1B · product UI foundation. No CRM, deals, quotations, logistics,
          financial integrations or AI agents are implemented yet.
        </p>
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
        <Link href="/status" className="inline-flex items-center gap-1.5 hover:text-mist-400">
          <ArrowUpRight className="size-3.5" aria-hidden />
          Public status page
        </Link>
      </footer>
    </div>
  );
}

function greeting(): string {
  const hour = new Date().getUTCHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

function Row({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className="shrink-0 text-[10px] uppercase tracking-[0.16em] text-mist-600">{label}</dt>
      <dd
        className={
          mono
            ? "min-w-0 break-all text-right font-mono text-[11px] text-mist-200"
            : "text-right text-[12px] text-mist-200"
        }
      >
        {value}
      </dd>
    </div>
  );
}
