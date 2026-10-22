"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { ArrowRight, Loader2, Send } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { transitionRfq } from "@/lib/sourcing/client";
import { etagFor, statusLabel } from "@/lib/sourcing/format";
import type { Rfq, RfqStatus } from "@/lib/sourcing/types";

const REASON_REQUIRED = new Set<RfqStatus>(["CANCELLED"]);
const SEND_TARGET = "SENT";

/**
 * Lifecycle actions for one RFQ.
 *
 * PREPARED and SENT are separate steps on purpose: the panel asks for the channel
 * and the evidence before it can dispatch, because "sent" without proof is a
 * claim, not a fact.
 */
export function RfqActions({
  rfq,
  csrfToken,
  canWrite,
}: {
  rfq: Rfq;
  csrfToken: string;
  canWrite: boolean;
}) {
  const router = useRouter();
  const [target, setTarget] = useState<RfqStatus | null>(null);
  const [channel, setChannel] = useState("email");
  const [evidence, setEvidence] = useState("");
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function apply(to: RfqStatus): Promise<void> {
    setError(null);
    setNotice(null);

    if (to === SEND_TARGET && (channel.trim().length < 2 || evidence.trim().length < 3)) {
      setError("Sending needs a channel and recorded evidence (for example the message id).");
      return;
    }
    if (REASON_REQUIRED.has(to) && reason.trim().length < 3) {
      setError("Cancelling an RFQ requires a reason of at least 3 characters.");
      return;
    }

    setPending(true);
    const result = await transitionRfq(
      rfq.id,
      {
        to,
        channel: to === SEND_TARGET ? channel.trim() : null,
        evidence: to === SEND_TARGET ? evidence.trim() : null,
        reason: REASON_REQUIRED.has(to) ? reason.trim() : null,
      },
      csrfToken,
      etagFor(rfq.version),
    );
    setPending(false);

    if (!result.ok) {
      setError(
        result.code === "VERSION_CONFLICT"
          ? `${result.message} Reload the RFQ before retrying.`
          : result.message,
      );
      return;
    }

    setTarget(null);
    setEvidence("");
    setReason("");
    setNotice(`RFQ moved to ${statusLabel(result.data.status)}.`);
    router.refresh();
  }

  if (!canWrite) {
    return (
      <Alert variant="info" title="Read-only access">
        Changing an RFQ requires <span className="font-mono">trade.write</span>.
      </Alert>
    );
  }

  if (rfq.allowed_transitions.length === 0) {
    return (
      <Alert variant="info" title={`RFQ ${statusLabel(rfq.status)}`}>
        No further transitions are available from this status.
      </Alert>
    );
  }

  return (
    <div className="space-y-3">
      {notice ? <Alert variant="success">{notice}</Alert> : null}
      {error ? <Alert variant="danger">{error}</Alert> : null}

      <div className="flex flex-wrap gap-2">
        {rfq.allowed_transitions.map((status) => (
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
            {status === SEND_TARGET ? (
              <Send className="size-3.5" aria-hidden />
            ) : (
              <ArrowRight className="size-3.5" aria-hidden />
            )}
            {status === "PREPARED" ? "Prepare snapshot" : statusLabel(status)}
          </Button>
        ))}
      </div>

      <p className="text-[11px] leading-relaxed text-mist-600">
        Preparing writes an immutable revision of the lines. Sending additionally records the
        channel, the time and the evidence that it left the building.
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
                setEvidence("");
              }}
            >
              Cancel
            </Button>
          </div>

          {target === SEND_TARGET ? (
            <div className="mt-3 space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="rfq-channel">Channel</Label>
                <Input
                  id="rfq-channel"
                  value={channel}
                  maxLength={40}
                  onChange={(event) => setChannel(event.target.value)}
                  placeholder="email"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="rfq-evidence">Evidence (required)</Label>
                <Input
                  id="rfq-evidence"
                  value={evidence}
                  maxLength={500}
                  onChange={(event) => setEvidence(event.target.value)}
                  placeholder="Message id or thread reference"
                />
              </div>
            </div>
          ) : null}

          {REASON_REQUIRED.has(target) ? (
            <div className="mt-3 space-y-1.5">
              <Label htmlFor="rfq-reason">Reason (required)</Label>
              <Textarea
                id="rfq-reason"
                value={reason}
                maxLength={500}
                onChange={(event) => setReason(event.target.value)}
                placeholder="Why is this RFQ being cancelled?"
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
