"use client";

import { Clock, Lock, ShieldCheck } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Meter } from "@/components/ui/meter";
import {
  MODE_META,
  RUN_STATUS_META,
  budgetPercent,
  describeErrorIn,
  formatTokens,
  formatUsdIn,
  humanTool,
  modeLabel,
  runStatusLabel,
} from "@/lib/ai/format";
import type { AiRun, AiStatus, AiToolList } from "@/lib/ai/types";
import { useLocale } from "@/lib/i18n/locale-provider";

export function ProviderStatusCard({
  status,
  companyName,
}: {
  status: AiStatus;
  companyName: string;
}) {
  const { t, locale } = useLocale();
  const mode = MODE_META[status.mode];
  const tokenPercent = budgetPercent(status.usage.tokens_today, status.usage.daily_token_budget);
  return (
    <section className="panel space-y-3 p-4" aria-label={t("sideProviderAria")}>
      <div className="flex items-center justify-between gap-2">
        <p className="eyebrow">{t("sideProvider")}</p>
        <Badge variant={mode.tone} dot>
          {modeLabel(t, status.mode)}
        </Badge>
      </div>

      <dl className="space-y-1.5 text-[11.5px]">
        <div className="flex justify-between gap-3">
          <dt className="text-mist-500">{t("sideCompany")}</dt>
          <dd className="truncate text-mist-200">{companyName}</dd>
        </div>
        {status.provider ? (
          <div className="flex justify-between gap-3">
            <dt className="text-mist-500">{t("sideModel")}</dt>
            <dd className="truncate font-mono text-[11px] text-mist-200">{status.model}</dd>
          </div>
        ) : null}
        <div className="flex justify-between gap-3">
          <dt className="text-mist-500">{t("sidePrompt")}</dt>
          <dd className="font-mono text-[11px] text-mist-300">{status.prompt_version}</dd>
        </div>
      </dl>

      <p className="text-[11px] leading-relaxed text-mist-400">{status.notice}</p>

      {status.external_processing ? (
        <Alert variant="warning" title={t("sideExternalTitle")}>
          {t("sideExternalBody")}
        </Alert>
      ) : null}

      {status.enabled ? (
        <div className="space-y-1.5">
          <div className="flex justify-between text-[11px]">
            <span className="text-mist-500">{t("sideTokens")}</span>
            <span className="font-mono text-mist-300">
              {formatTokens(status.usage.tokens_today)} /{" "}
              {formatTokens(status.usage.daily_token_budget)}
            </span>
          </div>
          <Meter
            value={tokenPercent}
            tone={tokenPercent > 85 ? "amber" : "accent"}
            label={t("sideBudgetLabel")}
          />
          <p className="text-[10.5px] text-mist-500">
            {t(status.usage.runs_today === 1 ? "sideRequestsOne" : "sideRequestsMany", {
              count: status.usage.runs_today,
              cost: formatUsdIn(status.usage.cost_usd_today, locale),
              budget: formatUsdIn(status.usage.daily_cost_budget_usd, locale),
            })}
          </p>
        </div>
      ) : null}

      <ul className="space-y-1 border-t border-white/5 pt-3 text-[11px] text-mist-400">
        <li className="flex items-center gap-1.5">
          <ShieldCheck className="size-3 text-jade-400" aria-hidden /> {t("sideReadOnly")}
        </li>
        <li className="flex items-center gap-1.5">
          <ShieldCheck className="size-3 text-jade-400" aria-hidden /> {t("sideNeverSends")}
        </li>
        <li className="flex items-center gap-1.5">
          <Clock className="size-3 text-mist-500" aria-hidden />
          {t("sideToolLimit", { count: status.limits.max_tool_calls_per_request })}
        </li>
      </ul>
    </section>
  );
}

export function ToolRegistryPanel({ tools }: { tools: AiToolList }) {
  const { t } = useLocale();
  return (
    <div className="space-y-4">
      <section aria-label={t("sideToolsAria")}>
        <p className="eyebrow mb-2">{t("sideReadOnlyTools")}</p>
        <ul className="space-y-2">
          {tools.tools.map((tool) => (
            <li key={tool.name} className="panel-inset p-2.5">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[12px] text-mist-200">{humanTool(tool.name)}</span>
                <Badge variant={tool.available ? "success" : "secondary"}>
                  {tool.available ? t("sideAvailable") : t("sideNoPermission")}
                </Badge>
              </div>
              <p className="mt-1 text-[11px] leading-relaxed text-mist-500">{tool.description}</p>
              <p className="mt-1 font-mono text-[10px] text-mist-500">
                {tool.permission} · {tool.tool_class}
              </p>
            </li>
          ))}
        </ul>
      </section>

      <section aria-label={t("sideApprovalAria")}>
        <p className="eyebrow mb-2">{t("sideApprovalClasses")}</p>
        <ul className="space-y-1.5">
          {tools.classes.map((item) => (
            <li key={item.name} className="text-[11px] leading-relaxed text-mist-400">
              <span className="font-mono text-[10px] text-mist-300">{item.name}</span> —{" "}
              {item.description}
            </li>
          ))}
        </ul>
      </section>

      <section aria-label={t("sideBlockedAria")}>
        <p className="eyebrow mb-2 flex items-center gap-1.5">
          <Lock className="size-3" aria-hidden /> {t("sideNeverAvailable")}
        </p>
        <ul className="space-y-1">
          {tools.blocked_actions.map((item) => (
            <li key={item.name} className="text-[11px] text-mist-500">
              <span className="font-mono text-[10px] text-crimson-400">{item.name}</span> —{" "}
              {item.reason}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

export function ActivityList({ runs }: { runs: readonly AiRun[] }) {
  const { t } = useLocale();
  if (runs.length === 0) {
    return <p className="text-[12px] text-mist-500">{t("sideNoRequests")}</p>;
  }
  return (
    <ol className="space-y-2" aria-label={t("sideActivityAria")}>
      {runs.map((run) => {
        const status = RUN_STATUS_META[run.status];
        return (
          <li key={run.id} className="panel-inset space-y-1 p-2.5">
            <div className="flex items-center justify-between gap-2">
              <span className="truncate text-[12px] text-mist-200">
                {run.conversation_title ?? t("sideConversation")}
              </span>
              <Badge variant={status.tone}>{runStatusLabel(t, run.status)}</Badge>
            </div>
            <p className="font-mono text-[10px] text-mist-500">
              {t(run.tool_call_count === 1 ? "sideToolCallOne" : "sideToolCallMany", {
                date: run.started_at.slice(0, 16).replace("T", " "),
                count: run.tool_call_count,
                tokens: formatTokens(run.input_tokens + run.output_tokens),
              })}
            </p>
            {run.error_code ? (
              <p className="text-[10.5px] text-amber-400">{describeErrorIn(t, run.error_code)}</p>
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}
