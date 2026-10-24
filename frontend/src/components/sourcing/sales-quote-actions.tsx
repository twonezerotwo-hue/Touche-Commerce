"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Check, Loader2, RotateCcw, Send, Undo2, X } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useLocale } from "@/lib/i18n/locale-provider";
import { sourcingStatusText } from "@/lib/i18n/value-labels";
import { actOnSalesQuote, type SalesQuoteAction } from "@/lib/sourcing/client";
import { etagFor } from "@/lib/sourcing/format";
import type { SalesQuote } from "@/lib/sourcing/types";

/**
 * The sales-quote workflow panel.
 *
 * `finance.approve` is shown only when the session holds it; the API enforces the
 * same rule, so hiding the button is convenience, never security. Approving your
 * own submission is refused by the service and explained here.
 */
export function SalesQuoteActions({
  quote,
  csrfToken,
  canWrite,
  canApprove,
}: {
  quote: SalesQuote;
  csrfToken: string;
  canWrite: boolean;
  canApprove: boolean;
}) {
  const router = useRouter();
  const { t } = useLocale();
  const [action, setAction] = useState<SalesQuoteAction | null>(null);
  const [reason, setReason] = useState("");
  const [validUntil, setValidUntil] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const transitions = quote.allowed_transitions;
  const canSubmit = quote.status === "DRAFT";
  const canWithdraw = transitions.includes("WITHDRAWN");
  const canDecide = quote.status === "PENDING_APPROVAL" && canApprove;
  const canRevise =
    quote.superseded_by_sales_quote_id === null &&
    ["APPROVED", "REJECTED", "WITHDRAWN"].includes(quote.status) &&
    canWrite;

  async function run(
    target: SalesQuoteAction,
    payload: Record<string, unknown> | null,
  ): Promise<void> {
    setError(null);
    setNotice(null);
    setPending(true);
    const result = await actOnSalesQuote(
      quote.id,
      target,
      payload,
      csrfToken,
      etagFor(quote.version),
    );
    setPending(false);

    if (!result.ok) {
      setError(
        result.code === "VERSION_CONFLICT"
          ? t("sqaVersionConflict", { message: result.message })
          : result.code === "FORBIDDEN"
            ? t("sqaForbidden", { message: result.message })
            : result.message,
      );
      return;
    }

    setAction(null);
    setReason("");
    setValidUntil("");
    setNotice(t("sqaNowStatus", { status: sourcingStatusText(t, result.data.status) }));
    router.refresh();
  }

  if (!canWrite && !canApprove) {
    return (
      <Alert variant="info" title={t("readOnlyAccess")}>
        {t("sqaReadOnly")}
      </Alert>
    );
  }

  return (
    <div className="space-y-3">
      {notice ? <Alert variant="success">{notice}</Alert> : null}
      {error ? <Alert variant="danger">{error}</Alert> : null}

      <div className="flex flex-wrap gap-2">
        {canSubmit && canWrite ? (
          <Button type="button" size="sm" disabled={pending} onClick={() => setAction("submit")}>
            <Send className="size-3.5" aria-hidden />
            {t("sqaSubmit")}
          </Button>
        ) : null}
        {canDecide ? (
          <>
            <Button type="button" size="sm" disabled={pending} onClick={() => setAction("approve")}>
              <Check className="size-3.5" aria-hidden />
              {t("sqaApprove")}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={pending}
              onClick={() => setAction("reject")}
            >
              <X className="size-3.5" aria-hidden />
              {t("sqaReject")}
            </Button>
          </>
        ) : null}
        {canWithdraw && canWrite ? (
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={pending}
            onClick={() => setAction("withdraw")}
          >
            <Undo2 className="size-3.5" aria-hidden />
            {t("sqaWithdraw")}
          </Button>
        ) : null}
        {canRevise ? (
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={pending}
            onClick={() => setAction("revisions")}
          >
            <RotateCcw className="size-3.5" aria-hidden />
            {t("sqaNewRevision")}
          </Button>
        ) : null}
      </div>

      {action === "submit" && !quote.can_submit ? (
        <Alert variant="info" title={t("sqaNotVerifiedTitle")}>
          {t("sqaNotVerifiedBody", { status: sourcingStatusText(t, quote.scenario_status) })}
        </Alert>
      ) : null}

      {action ? (
        <div className="rounded-lg border border-white/[0.07] bg-white/[0.015] p-3">
          <p className="text-[12.5px] text-mist-200">
            {action === "submit" ? t("sqaAskSubmit") : null}
            {action === "approve" ? t("sqaAskApprove") : null}
            {action === "reject" ? t("sqaAskReject") : null}
            {action === "withdraw" ? t("sqaAskWithdraw") : null}
            {action === "revisions" ? t("sqaAskRevision") : null}
          </p>

          {action === "reject" ? (
            <div className="mt-2 space-y-1.5">
              <Label htmlFor="sq-reason">{t("sqaReasonRequired")}</Label>
              <Textarea
                id="sq-reason"
                value={reason}
                maxLength={500}
                onChange={(event) => setReason(event.target.value)}
                placeholder={t("sqaRejectPlaceholder")}
              />
            </div>
          ) : null}

          {action === "withdraw" ? (
            <div className="mt-2 space-y-1.5">
              <Label htmlFor="sq-withdraw-reason">{t("sqaReasonOptional")}</Label>
              <Input
                id="sq-withdraw-reason"
                value={reason}
                maxLength={500}
                onChange={(event) => setReason(event.target.value)}
              />
            </div>
          ) : null}

          {action === "revisions" ? (
            <div className="mt-2 space-y-1.5">
              <Label htmlFor="sq-valid-until">{t("sqaNewValidity")}</Label>
              <Input
                id="sq-valid-until"
                type="date"
                value={validUntil}
                onChange={(event) => setValidUntil(event.target.value)}
              />
            </div>
          ) : null}

          <div className="mt-3 flex items-center gap-2">
            <Button
              type="button"
              size="sm"
              disabled={pending}
              onClick={() => {
                if (action === "reject" && reason.trim().length < 3) {
                  setError(t("sqaRejectNeedsReason"));
                  return;
                }
                if (action === "revisions" && !validUntil) {
                  setError(t("sqaChooseValidity"));
                  return;
                }
                void run(
                  action,
                  action === "reject"
                    ? { reason: reason.trim() }
                    : action === "withdraw"
                      ? { reason: reason.trim() || null }
                      : action === "revisions"
                        ? { valid_until: validUntil, reason: reason.trim() || null }
                        : {},
                );
              }}
            >
              {pending ? <Loader2 className="size-3.5 animate-spin" aria-hidden /> : null}
              {pending ? t("sqaApplying") : t("sqaConfirm")}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              disabled={pending}
              onClick={() => {
                setAction(null);
                setReason("");
                setValidUntil("");
              }}
            >
              {t("actionCancel")}
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
