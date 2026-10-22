"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Loader2 } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { transitionPurchaseOrder } from "@/lib/operations/client";
import { operationsStatusLabel } from "@/lib/operations/format";
import type { PurchaseOrder } from "@/lib/operations/types";
import { etagFor } from "@/lib/sourcing/format";

/**
 * Purchase-order workflow.
 *
 * The system never sends anything. `RECORDED_SENT` records that a human sent it
 * elsewhere and must carry the channel, timestamp and external reference;
 * `SUPPLIER_CONFIRMED` records the supplier's own acknowledgement.
 */
export function PurchaseOrderActions({
  purchaseOrder,
  csrfToken,
  canWrite,
  canApprove,
}: {
  purchaseOrder: PurchaseOrder;
  csrfToken: string;
  canWrite: boolean;
  canApprove: boolean;
}) {
  const router = useRouter();
  const [target, setTarget] = useState<string | null>(null);
  const [channel, setChannel] = useState("EMAIL");
  const [reference, setReference] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const options = purchaseOrder.allowed_transitions.filter(
    (value) => value !== "APPROVED" || canApprove,
  );

  async function apply(): Promise<void> {
    if (!target) return;
    if (target !== "APPROVED" && !canWrite) {
      setError("Recording a purchase-order transition requires trade.write.");
      return;
    }
    if (target === "RECORDED_SENT" && reference.trim().length < 2) {
      setError("Record the external reference (message id, WhatsApp export, portal receipt).");
      return;
    }
    if (target === "SUPPLIER_CONFIRMED" && confirmation.trim().length < 2) {
      setError("Record the supplier's confirmation reference.");
      return;
    }
    if (target === "CANCELLED" && reason.trim().length < 3) {
      setError("A cancellation needs a reason of at least 3 characters.");
      return;
    }

    setPending(true);
    setError(null);
    const result = await transitionPurchaseOrder(
      purchaseOrder.id,
      {
        target,
        reason: reason.trim() || null,
        dispatched_at: target === "RECORDED_SENT" ? new Date().toISOString() : null,
        dispatch_channel: target === "RECORDED_SENT" ? channel : null,
        dispatch_reference: target === "RECORDED_SENT" ? reference.trim() : null,
        supplier_confirmation_reference:
          target === "SUPPLIER_CONFIRMED" ? confirmation.trim() : null,
        evidence_reference: target === "SUPPLIER_CONFIRMED" ? confirmation.trim() : null,
      },
      csrfToken,
      etagFor(purchaseOrder.version),
    );
    setPending(false);

    if (!result.ok) {
      setError(
        result.code === "FORBIDDEN"
          ? `${result.message} Approval needs finance.approve and a different person from the creator.`
          : result.message,
      );
      return;
    }
    setTarget(null);
    setReference("");
    setConfirmation("");
    setReason("");
    setNotice(`Purchase order is now ${operationsStatusLabel(result.data.status).toLowerCase()}.`);
    router.refresh();
  }

  if (options.length === 0) {
    return (
      <Alert variant="info" title="No further transitions">
        This purchase order is {operationsStatusLabel(purchaseOrder.status).toLowerCase()} and
        cannot move again.
      </Alert>
    );
  }

  return (
    <div className="space-y-3">
      {notice ? <Alert variant="success">{notice}</Alert> : null}
      {error ? <Alert variant="danger">{error}</Alert> : null}

      <div className="flex flex-wrap gap-2">
        {options.map((value) => (
          <Button
            key={value}
            type="button"
            size="sm"
            variant={
              value === "CANCELLED" ? "danger" : value === "APPROVED" ? "default" : "outline"
            }
            onClick={() => setTarget(value)}
          >
            {value === "APPROVED"
              ? "Approve purchase order"
              : `Mark ${operationsStatusLabel(value).toLowerCase()}`}
          </Button>
        ))}
      </div>

      {target ? (
        <div className="rounded-lg border border-white/[0.07] bg-white/[0.015] p-3">
          <p className="text-[12.5px] text-mist-200">
            {target === "RECORDED_SENT"
              ? "Record that you sent this order outside the platform. Nothing is transmitted by TOUCHE."
              : target === "SUPPLIER_CONFIRMED"
                ? "Record the supplier's acknowledgement. This is evidence, not an automated status."
                : target === "APPROVED"
                  ? "Approving is a financial act requiring finance.approve; the creator cannot approve their own order."
                  : `Move this purchase order to ${operationsStatusLabel(target).toLowerCase()}?`}
          </p>

          {target === "RECORDED_SENT" ? (
            <div className="mt-2 grid gap-2 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="po-channel">Channel</Label>
                <Input
                  id="po-channel"
                  value={channel}
                  maxLength={32}
                  onChange={(event) => setChannel(event.target.value)}
                  placeholder="EMAIL, WHATSAPP, PORTAL"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="po-reference">External reference</Label>
                <Input
                  id="po-reference"
                  value={reference}
                  maxLength={200}
                  onChange={(event) => setReference(event.target.value)}
                  placeholder="Message id or portal receipt"
                />
              </div>
            </div>
          ) : null}

          {target === "SUPPLIER_CONFIRMED" ? (
            <div className="mt-2 space-y-1.5">
              <Label htmlFor="po-confirmation">Supplier confirmation reference</Label>
              <Input
                id="po-confirmation"
                value={confirmation}
                maxLength={200}
                onChange={(event) => setConfirmation(event.target.value)}
                placeholder="Supplier acknowledgement id"
              />
            </div>
          ) : null}

          {target === "CANCELLED" ? (
            <div className="mt-2 space-y-1.5">
              <Label htmlFor="po-reason">Reason (required)</Label>
              <Textarea
                id="po-reason"
                value={reason}
                maxLength={500}
                onChange={(event) => setReason(event.target.value)}
              />
            </div>
          ) : null}

          <div className="mt-3 flex items-center gap-2">
            <Button type="button" size="sm" disabled={pending} onClick={() => void apply()}>
              {pending ? <Loader2 className="size-3.5 animate-spin" aria-hidden /> : null}
              {pending ? "Applying…" : "Confirm"}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              disabled={pending}
              onClick={() => {
                setTarget(null);
                setError(null);
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
