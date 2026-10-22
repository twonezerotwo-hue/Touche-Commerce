"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Loader2, PencilLine, XCircle } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
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
          ? `${result.message} Reload the order before retrying.`
          : result.code === "REASON_REQUIRED"
            ? "A cancellation needs a written reason of at least 3 characters."
            : result.message,
      );
      return;
    }
    setMode(null);
    setReason("");
    setNotice(`Order is now ${result.data.status.replaceAll("_", " ").toLowerCase()}.`);
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
    setNotice("Amendment recorded. The accepted commercial snapshot is unchanged.");
    router.refresh();
  }

  if (!canWrite) {
    return (
      <Alert variant="info" title="Read-only access">
        Changing an order requires <span className="font-mono">trade.write</span>.
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
            Close order
          </Button>
        ) : null}
        {order.status !== "CANCELLED" && !canClose ? (
          <Button type="button" size="sm" variant="outline" onClick={() => setMode("amend")}>
            <PencilLine className="size-3.5" aria-hidden />
            Record amendment
          </Button>
        ) : null}
        {canCancel ? (
          <Button type="button" size="sm" variant="danger" onClick={() => setMode("cancel")}>
            <XCircle className="size-3.5" aria-hidden />
            Cancel order
          </Button>
        ) : null}
      </div>

      {mode ? (
        <div className="rounded-lg border border-white/[0.07] bg-white/[0.015] p-3">
          <p className="text-[12.5px] text-mist-200">
            {mode === "cancel"
              ? "Cancellation is recorded with a reason. The accepted quote and the WON transition stay intact; nothing is rewritten."
              : mode === "close"
                ? "Closing records that operational work is complete. It does not post revenue, settle payment or create an accounting entry."
                : "Amendment changes are appended to the order history; the accepted terms snapshot is never overwritten."}
          </p>

          {mode === "amend" ? (
            <div className="mt-2 space-y-1.5">
              <Label htmlFor="order-payment-terms">New payment terms (optional)</Label>
              <Input
                id="order-payment-terms"
                value={paymentTerms}
                maxLength={200}
                onChange={(event) => setPaymentTerms(event.target.value)}
                placeholder="60 days net"
              />
            </div>
          ) : null}

          {mode === "cancel" || mode === "amend" ? (
            <div className="mt-2 space-y-1.5">
              <Label htmlFor="order-reason">Reason (required)</Label>
              <Textarea
                id="order-reason"
                value={reason}
                maxLength={500}
                onChange={(event) => setReason(event.target.value)}
                placeholder={
                  mode === "cancel"
                    ? "Why is the customer's order cancelled?"
                    : "What changed and why?"
                }
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
                  setError("A cancellation requires a reason of at least 3 characters.");
                  return;
                }
                if (mode === "amend") {
                  if (reason.trim().length < 3) {
                    setError("An amendment requires a reason.");
                    return;
                  }
                  void amend();
                  return;
                }
                void transition(mode === "close" ? "CLOSED" : "CANCELLED", reason.trim() || null);
              }}
            >
              {pending ? <Loader2 className="size-3.5 animate-spin" aria-hidden /> : null}
              {pending ? "Applying…" : "Confirm"}
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
              Cancel
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
