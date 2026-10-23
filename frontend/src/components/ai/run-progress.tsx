import { Loader2, ShieldAlert, Wrench } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { RUN_STATUS_META, TOOL_STATUS_META, describeError, humanTool } from "@/lib/ai/format";
import type { AiRun } from "@/lib/ai/types";

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
  const running = run.status === "RUNNING";
  const status = RUN_STATUS_META[run.status];
  return (
    <section
      aria-label="Tool execution"
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
          <p className="text-[12px] text-mist-200">
            {running ? "Reading your records…" : "Records read"}
          </p>
          <Badge variant={status.tone}>{status.label}</Badge>
        </div>
        {running && onCancel ? (
          <Button
            type="button"
            size="xs"
            variant="outline"
            onClick={onCancel}
            disabled={cancelling}
          >
            {cancelling ? "Cancelling…" : "Cancel"}
          </Button>
        ) : null}
      </div>

      {run.tool_calls.length === 0 ? (
        <p className="text-[11px] text-mist-500">
          {running ? "Waiting for the first tool call." : "No tools were called."}
        </p>
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
                    <ShieldAlert className="size-3 text-crimson-400" aria-label="Blocked action" />
                  ) : null}
                </span>
                <span className="flex shrink-0 items-center gap-2">
                  <span className="font-mono text-[10px] text-mist-500">{call.duration_ms} ms</span>
                  <Badge variant={meta.tone}>{meta.label}</Badge>
                </span>
              </li>
            );
          })}
        </ol>
      )}

      {run.status === "FAILED" || run.status === "CANCELLED" ? (
        <Alert variant={run.status === "FAILED" ? "danger" : "info"}>
          {describeError(run.error_code)}
        </Alert>
      ) : null}

      {run.safety_flags.length > 0 ? (
        <p className="text-[10.5px] leading-relaxed text-amber-400">
          Safety check:{" "}
          {run.safety_flags.map((f) => f.replaceAll("_", " ").toLowerCase()).join(", ")}.
          Instruction-like text found in records was withheld from the assistant.
        </p>
      ) : null}

      <p className="font-mono text-[10px] text-mist-500">
        {run.provider} · {run.model} · {run.input_tokens + run.output_tokens} tokens ·{" "}
        {run.model_steps} step{run.model_steps === 1 ? "" : "s"}
      </p>
    </section>
  );
}
