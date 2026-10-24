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
import { useLocale } from "@/lib/i18n/locale-provider";
import { sourcingStatusText } from "@/lib/i18n/value-labels";
import { etagFor } from "@/lib/sourcing/format";
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
  const { t } = useLocale();
  const statusLabel = (value: string): string => sourcingStatusText(t, value);
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
      setError(t("rfqaNeedsEvidence"));
      return;
    }
    if (REASON_REQUIRED.has(to) && reason.trim().length < 3) {
      setError(t("rfqaCancelNeedsReason"));
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
          ? t("rfqaVersionConflict", { message: result.message })
          : result.message,
      );
      return;
    }

    setTarget(null);
    setEvidence("");
    setReason("");
    setNotice(t("rfqaMoved", { status: statusLabel(result.data.status) }));
    router.refresh();
  }

  if (!canWrite) {
    return (
      <Alert variant="info" title={t("readOnlyAccess")}>
        {t("rfqaReadOnly")}
      </Alert>
    );
  }

  if (rfq.allowed_transitions.length === 0) {
    return (
      <Alert variant="info" title={t("rfqaStatusTitle", { status: statusLabel(rfq.status) })}>
        {t("rfqaNoTransitions")}
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
            {status === "PREPARED" ? t("rfqaPrepare") : statusLabel(status)}
          </Button>
        ))}
      </div>

      <p className="text-[11px] leading-relaxed text-mist-600">{t("rfqaHint")}</p>

      {target ? (
        <div className="rounded-lg border border-white/[0.07] bg-white/[0.015] p-3">
          <div className="flex items-center justify-between gap-3">
            <p className="text-[12.5px] text-mist-200">
              {t("rfqaMoveTo")} <span className="font-medium">{statusLabel(target)}</span>
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
              {t("actionCancel")}
            </Button>
          </div>

          {target === SEND_TARGET ? (
            <div className="mt-3 space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="rfq-channel">{t("rfqaChannel")}</Label>
                <Input
                  id="rfq-channel"
                  value={channel}
                  maxLength={40}
                  onChange={(event) => setChannel(event.target.value)}
                  placeholder={t("rfqaChannelPlaceholder")}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="rfq-evidence">{t("rfqaEvidence")}</Label>
                <Input
                  id="rfq-evidence"
                  value={evidence}
                  maxLength={500}
                  onChange={(event) => setEvidence(event.target.value)}
                  placeholder={t("rfqaEvidencePlaceholder")}
                />
              </div>
            </div>
          ) : null}

          {REASON_REQUIRED.has(target) ? (
            <div className="mt-3 space-y-1.5">
              <Label htmlFor="rfq-reason">{t("rfqaReason")}</Label>
              <Textarea
                id="rfq-reason"
                value={reason}
                maxLength={500}
                onChange={(event) => setReason(event.target.value)}
                placeholder={t("rfqaReasonPlaceholder")}
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
            {pending ? t("rfqaApplying") : t("rfqaConfirm", { status: statusLabel(target) })}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
