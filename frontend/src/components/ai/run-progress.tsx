"use client";

import { Loader2, ShieldAlert, Wrench } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  RUN_STATUS_META,
  TOOL_STATUS_META,
  describeErrorIn,
  humanTool,
  runStatusLabel,
  toolStatusLabel,
} from "@/lib/ai/format";
import type { AiRun } from "@/lib/ai/types";
import { useLocale } from "@/lib/i18n/locale-provider";

/** Live tool-execution status for one request (also used for finished runs). */
export function RunProgress({
  run,
  onCancel,
  cancelling = false,
}: {
  run: AiRun;
  onCancel?: () => void;
  cancelling?: boolean;
}) {
  const { t } = useLocale();
  const running = run.status === "RUNNING";
  const status = RUN_STATUS_META[run.status];
  return (
    <section
      aria-label={t("runToolAria")}
      aria-live="polite"
      className="panel-inset space-y-2.5 p-3"
      data-run-status={run.status}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          {running ? (
            <Loader2 className="size-3.5 animate-spin text-accent-300" aria-hidden />
          ) : (
            <Wrench className="size-3.5 text-mist-500" aria-hidden />
          )}
          <p className="text-[12px] text-mist-200">{running ? t("runReading") : t("runRead")}</p>
          <Badge variant={status.tone}>{runStatusLabel(t, run.status)}</Badge>
        </div>
        {running && onCancel ? (
          <Button
            type="button"
            size="xs"
            variant="outline"
            onClick={onCancel}
            disabled={cancelling}
          >
            {cancelling ? t("runCancelling") : t("runCancel")}
          </Button>
        ) : null}
      </div>

      {run.tool_calls.length === 0 ? (
        <p className="text-[11px] text-mist-500">{running ? t("runWaiting") : t("runNoTools")}</p>
      ) : (
        <ol className="space-y-1">
          {run.tool_calls.map((call) => {
            const meta = TOOL_STATUS_META[call.status];
            return (
              <li
                key={call.ordinal}
                className="flex items-center justify-between gap-3 text-[11.5px]"
              >
                <span className="flex min-w-0 items-center gap-2">
                  <span className="font-mono text-[10px] text-mist-500">{call.ordinal}</span>
                  <span className="truncate text-mist-300">{humanTool(call.tool_name)}</span>
                  {call.tool_class === "BLOCKED" ? (
                    <ShieldAlert
                      className="size-3 text-crimson-400"
                      aria-label={t("runBlockedAria")}
                    />
                  ) : null}
                </span>
                <span className="flex shrink-0 items-center gap-2">
                  <span className="font-mono text-[10px] text-mist-500">{call.duration_ms} ms</span>
                  <Badge variant={meta.tone}>{toolStatusLabel(t, call.status)}</Badge>
                </span>
              </li>
            );
          })}
        </ol>
      )}

      {run.status === "FAILED" || run.status === "CANCELLED" ? (
        <Alert variant={run.status === "FAILED" ? "danger" : "info"}>
          {describeErrorIn(t, run.error_code)}
        </Alert>
      ) : null}

      {run.safety_flags.length > 0 ? (
        <p className="text-[10.5px] leading-relaxed text-amber-400">
          {t("runSafety", {
            flags: run.safety_flags.map((f) => f.replaceAll("_", " ").toLowerCase()).join(", "),
          })}
        </p>
      ) : null}

      <p className="font-mono text-[10px] text-mist-500">
        {t("runMeta", {
          provider: run.provider,
          model: run.model,
          tokens: run.input_tokens + run.output_tokens,
          steps: t(run.model_steps === 1 ? "runStepOne" : "runStepMany", {
            count: run.model_steps,
          }),
        })}
      </p>
    </section>
  );
}
