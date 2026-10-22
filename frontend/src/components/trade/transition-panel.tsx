"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { ArrowRight, Loader2, Lock } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { transitionDeal } from "@/lib/trade/client";
import { statusLabel } from "@/lib/trade/format";
import type { Deal, DealStatus } from "@/lib/trade/types";

const TERMINAL = new Set<DealStatus>(["WON", "LOST", "CANCELLED"]);
const REASON_REQUIRED = new Set<DealStatus>(["LOST", "CANCELLED"]);

export function TransitionPanel({
  deal,
  csrfToken,
  canWrite,
}: {
  deal: Deal;
  csrfToken: string;
  canWrite: boolean;
}) {
  const router = useRouter();
  const [target, setTarget] = useState<DealStatus | null>(null);
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const allowed = deal.allowed_transitions;

  async function apply(to: DealStatus): Promise<void> {
    setError(null);
    setNotice(null);
    if (REASON_REQUIRED.has(to) && reason.trim().length < 3) {
      setError("A reason of at least 3 characters is required to lose or cancel a deal.");
      return;
    }
    setPending(true);
    const result = await transitionDeal(
      deal.id,
      { to, reason: REASON_REQUIRED.has(to) ? reason.trim() : null },
      csrfToken,
      `"v${deal.version}"`,
    );
    setPending(false);

    if (!result.ok) {
      setError(
        result.code === "VERSION_CONFLICT"
          ? `${result.message} Another user changed this deal. Reload before retrying.`
          : result.requestId
            ? `${result.message} (request ${result.requestId})`
            : result.message,
      );
      return;
    }
    setTarget(null);
    setReason("");
    setNotice(`Deal moved to ${statusLabel(result.data.status)}.`);
    router.refresh();
  }

  if (!canWrite) {
    return (
      <Alert variant="info" title="Read-only access">
        Moving a deal requires <span className="font-mono">trade.write</span>.
      </Alert>
    );
  }

  if (TERMINAL.has(deal.status)) {
    return (
      <Alert variant="info" title="Closed deal">
        {statusLabel(deal.status)} is a terminal status; no further transitions are possible.
      </Alert>
    );
  }

  return (
    <div className="space-y-3">
      {notice ? <Alert variant="success">{notice}</Alert> : null}
      {error ? <Alert variant="danger">{error}</Alert> : null}

      <div className="flex flex-wrap gap-2">
        {allowed.map((status) => (
          <Button
            key={status}
            type="button"
            size="sm"
            variant={target === status ? "default" : "outline"}
            disabled={pending}
            onClick={() => {
              setError(null);
              setNotice(null);
              setTarget(status);
            }}
          >
            {statusLabel(status)}
            <ArrowRight className="size-3.5" aria-hidden />
          </Button>
        ))}
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled
          title="Disabled until sales orders exist"
        >
          <Lock className="size-3.5" aria-hidden />
          Won
        </Button>
      </div>

      <p className="text-[11px] leading-relaxed text-mist-600">
        Won is disabled until the sales order module exists: a deal may not claim a win without an
        order behind it.
      </p>

      {target ? (
        <div className="rounded-lg border border-white/[0.07] bg-white/[0.015] p-3">
          <div className="flex items-center justify-between gap-3">
            <p className="text-[12.5px] text-mist-200">
              Move to <span className="font-medium">{statusLabel(target)}</span>
            </p>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => {
                setTarget(null);
                setReason("");
              }}
            >
              Cancel
            </Button>
          </div>

          {REASON_REQUIRED.has(target) ? (
            <div className="mt-3 space-y-1.5">
              <Label htmlFor="transition-reason">Reason (required)</Label>
              <Textarea
                id="transition-reason"
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                maxLength={500}
                placeholder="Why is this deal being closed?"
              />
            </div>
          ) : null}

          <Button
            type="button"
            size="sm"
            className="mt-3"
            disabled={pending}
            onClick={() => apply(target)}
          >
            {pending ? <Loader2 className="size-3.5 animate-spin" aria-hidden /> : null}
            {pending ? "Applying…" : `Confirm ${statusLabel(target)}`}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
