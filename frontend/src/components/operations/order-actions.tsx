"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Loader2, PencilLine, XCircle } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useLocale } from "@/lib/i18n/locale-provider";
import { operationsStatusText } from "@/lib/i18n/value-labels";
import { amendSalesOrder, transitionSalesOrder } from "@/lib/operations/client";
import { etagFor } from "@/lib/sourcing/format";
import type { SalesOrder } from "@/lib/operations/types";

/**
 * Order lifecycle controls.
 *
 * `FULFILLED` is never offered here: it is derived from delivered shipment
 * quantities. Closing an order is an administrative act, not a payment event.
 */
export function OrderActions({
  order,
  csrfToken,
  canWrite,
}: {
  order: SalesOrder;
  csrfToken: string;
  canWrite: boolean;
}) {
  const router = useRouter();
  const { t, locale } = useLocale();
  const [mode, setMode] = useState<"cancel" | "amend" | "close" | null>(null);
  const [reason, setReason] = useState("");
  const [paymentTerms, setPaymentTerms] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const canClose = order.allowed_transitions.includes("CLOSED");
  const canCancel = order.allowed_transitions.includes("CANCELLED");

  async function transition(target: string, value: string | null): Promise<void> {
    setPending(true);
    setError(null);
    const result = await transitionSalesOrder(
      order.id,
      target,
      value,
      csrfToken,
      etagFor(order.version),
    );
    setPending(false);
    if (!result.ok) {
      setError(
        result.code === "VERSION_CONFLICT"
          ? t("oaConflict", { message: result.message })
          : result.code === "REASON_REQUIRED"
            ? t("oaCancelReasonServer")
            : result.message,
      );
      return;
    }
    setMode(null);
    setReason("");
    setNotice(
      t("oaNowStatus", {
        status: operationsStatusText(t, result.data.status).toLocaleLowerCase(locale),
      }),
    );
    router.refresh();
  }

  async function amend(): Promise<void> {
    setPending(true);
    setError(null);
    const result = await amendSalesOrder(
      order.id,
      { reason: reason.trim(), payment_terms: paymentTerms.trim() || undefined },
      csrfToken,
      etagFor(order.version),
    );
    setPending(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    setMode(null);
    setReason("");
    setPaymentTerms("");
    setNotice(t("oaAmended"));
    router.refresh();
  }

  if (!canWrite) {
    return (
      <Alert variant="info" title={t("readOnlyAccess")}>
        {t("oaReadOnly")}
      </Alert>
    );
  }

  return (
    <div className="space-y-3">
      {notice ? <Alert variant="success">{notice}</Alert> : null}
      {error ? <Alert variant="danger">{error}</Alert> : null}

      <div className="flex flex-wrap gap-2">
        {canClose ? (
          <Button type="button" size="sm" variant="outline" onClick={() => setMode("close")}>
            {t("oaClose")}
          </Button>
        ) : null}
        {order.status !== "CANCELLED" && !canClose ? (
          <Button type="button" size="sm" variant="outline" onClick={() => setMode("amend")}>
            <PencilLine className="size-3.5" aria-hidden />
            {t("oaAmend")}
          </Button>
        ) : null}
        {canCancel ? (
          <Button type="button" size="sm" variant="danger" onClick={() => setMode("cancel")}>
            <XCircle className="size-3.5" aria-hidden />
            {t("oaCancel")}
          </Button>
        ) : null}
      </div>

      {mode ? (
        <div className="rounded-lg border border-white/[0.07] bg-white/[0.015] p-3">
          <p className="text-[12.5px] text-mist-200">
            {mode === "cancel"
              ? t("oaCancelNote")
              : mode === "close"
                ? t("oaCloseNote")
                : t("oaAmendNote")}
          </p>

          {mode === "amend" ? (
            <div className="mt-2 space-y-1.5">
              <Label htmlFor="order-payment-terms">{t("oaNewTerms")}</Label>
              <Input
                id="order-payment-terms"
                value={paymentTerms}
                maxLength={200}
                onChange={(event) => setPaymentTerms(event.target.value)}
                placeholder={t("oaTermsPlaceholder")}
              />
            </div>
          ) : null}

          {mode === "cancel" || mode === "amend" ? (
            <div className="mt-2 space-y-1.5">
              <Label htmlFor="order-reason">{t("tpReason")}</Label>
              <Textarea
                id="order-reason"
                value={reason}
                maxLength={500}
                onChange={(event) => setReason(event.target.value)}
                placeholder={mode === "cancel" ? t("oaWhyCancelled") : t("oaWhatChanged")}
              />
            </div>
          ) : null}

          <div className="mt-3 flex items-center gap-2">
            <Button
              type="button"
              size="sm"
              disabled={pending}
              onClick={() => {
                if (mode === "cancel" && reason.trim().length < 3) {
                  setError(t("oaCancelReason"));
                  return;
                }
                if (mode === "amend") {
                  if (reason.trim().length < 3) {
                    setError(t("oaAmendReason"));
                    return;
                  }
                  void amend();
                  return;
                }
                void transition(mode === "close" ? "CLOSED" : "CANCELLED", reason.trim() || null);
              }}
            >
              {pending ? <Loader2 className="size-3.5 animate-spin" aria-hidden /> : null}
              {pending ? t("tpApplying") : t("oaConfirm")}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              disabled={pending}
              onClick={() => {
                setMode(null);
                setReason("");
                setPaymentTerms("");
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
