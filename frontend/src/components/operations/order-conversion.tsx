"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { AlertTriangle, FileCheck2, Loader2 } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { convertDealToOrder, recordCustomerAcceptance } from "@/lib/operations/client";
import { newIdempotencyKey } from "@/lib/sourcing/client";
import type { CustomerAcceptance, SalesQuoteOption } from "@/lib/operations/types";

const CHANNELS = ["SIGNED_QUOTE", "PURCHASE_ORDER", "EMAIL", "PORTAL", "OTHER"] as const;

function nowLocal(): string {
  const date = new Date();
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

/**
 * Customer acceptance and the atomic conversion that wins the deal.
 *
 * The panel deliberately separates the two facts: the quote is already approved
 * internally, and acceptance is a *customer* act with a channel, a timestamp and
 * an evidence reference. The API refuses the conversion without it.
 */
export function OrderConversionPanel({
  dealId,
  quotes,
  acceptances,
  csrfToken,
  canWrite,
  brokerage,
  onBrokerageChange,
}: {
  dealId: string;
  quotes: SalesQuoteOption[];
  acceptances: CustomerAcceptance[];
  csrfToken: string;
  canWrite: boolean;
  brokerage: boolean;
  onBrokerageChange: (value: boolean) => void;
}) {
  const router = useRouter();
  const approved = quotes.filter((quote) => quote.status === "APPROVED");
  const [quoteId, setQuoteId] = useState(approved[0]?.id ?? "");
  const [channel, setChannel] = useState<string>("SIGNED_QUOTE");
  const [acceptedAt, setAcceptedAt] = useState(nowLocal());
  const [acceptedBy, setAcceptedBy] = useState("");
  const [reference, setReference] = useState("");
  const [notes, setNotes] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [conversionKey] = useState(() => newIdempotencyKey());

  const existing = acceptances.find((item) => item.sales_quote_id === quoteId) ?? null;

  async function recordAndConvert(): Promise<void> {
    setError(null);
    setNotice(null);
    if (!quoteId) {
      setError("Select the approved quote revision the customer accepted.");
      return;
    }
    if (!existing) {
      if (acceptedBy.trim().length < 2) {
        setError("Record who accepted on the customer side.");
        return;
      }
      if (reference.trim().length < 3) {
        setError("An evidence reference is required (signed quote, PO number, portal receipt).");
        return;
      }
    }

    setPending(true);
    let evidenceId = existing?.id ?? null;
    if (!evidenceId) {
      const acceptance = await recordCustomerAcceptance(
        dealId,
        {
          channel,
          accepted_at: new Date(acceptedAt).toISOString(),
          accepted_by_name: acceptedBy.trim(),
          evidence_reference: reference.trim(),
          notes: notes.trim() || null,
        },
        csrfToken,
      );
      if (!acceptance.ok) {
        setPending(false);
        setError(
          acceptance.code === "CONFLICT"
            ? `${acceptance.message} Approve the exact quote revision first.`
            : acceptance.message,
        );
        return;
      }
      evidenceId = acceptance.data.id;
      setNotice("Customer acceptance recorded. Converting the deal…");
    }

    const conversion = await convertDealToOrder(
      dealId,
      { sales_quote_id: quoteId, acceptance_evidence_id: evidenceId },
      csrfToken,
      conversionKey,
    );
    setPending(false);

    if (!conversion.ok) {
      setError(
        conversion.code === "ALREADY_WON"
          ? "This deal already has a sales order. Open it from Orders."
          : conversion.code === "IDEMPOTENCY_CONFLICT"
            ? "This conversion was already submitted with different terms. Reload the deal."
            : conversion.message,
      );
      return;
    }

    router.push(`/orders/${conversion.data.id}`);
    router.refresh();
  }

  if (!canWrite) {
    return (
      <Alert variant="info" title="Read-only access">
        Converting a deal requires <span className="font-mono">trade.write</span>.
      </Alert>
    );
  }

  if (approved.length === 0) {
    return (
      <Alert variant="info" title="No approved quote">
        An order can only be created from an approved sales quote revision. Submit the quote and
        have a second person approve it.
      </Alert>
    );
  }

  return (
    <div className="space-y-3">
      <Alert variant="warning" title="Approval is not acceptance">
        TOUCHE approving a quote does not prove the customer accepted it. Record the customer’s
        channel, timestamp and evidence reference — the conversion is refused without them.
      </Alert>

      {notice ? <Alert variant="success">{notice}</Alert> : null}
      {error ? <Alert variant="danger">{error}</Alert> : null}

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="convert-quote">Approved quote revision</Label>
          <Select
            id="convert-quote"
            value={quoteId}
            onChange={(event) => setQuoteId(event.target.value)}
          >
            {approved.map((quote) => (
              <option key={quote.id} value={quote.id}>
                {quote.quote_number} r{quote.revision} · {quote.currency} {quote.total_value}
              </option>
            ))}
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="convert-model">Commercial model</Label>
          <Select
            id="convert-model"
            value={brokerage ? "BROKERAGE" : "PURCHASE_RESALE"}
            onChange={(event) => onBrokerageChange(event.target.value === "BROKERAGE")}
          >
            <option value="PURCHASE_RESALE">Purchase and resale (TOUCHE buys)</option>
            <option value="BROKERAGE">Brokerage / sourcing (TOUCHE does not buy)</option>
          </Select>
          <p className="text-[10.5px] leading-relaxed text-mist-600">
            Brokerage orders never require a supplier purchase order.
          </p>
        </div>
      </div>

      {existing ? (
        <Alert variant="success" title="Acceptance already recorded">
          {existing.accepted_by_name} accepted r{existing.sales_quote_revision} via{" "}
          {existing.channel.replaceAll("_", " ").toLowerCase()} on{" "}
          {new Date(existing.accepted_at).toLocaleString("en-GB")}. Evidence:{" "}
          <span className="font-mono text-[11px]">{existing.evidence_reference}</span>
        </Alert>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="acceptance-channel">Channel</Label>
            <Select
              id="acceptance-channel"
              value={channel}
              onChange={(event) => setChannel(event.target.value)}
            >
              {CHANNELS.map((option) => (
                <option key={option} value={option}>
                  {option.replaceAll("_", " ").toLowerCase()}
                </option>
              ))}
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="acceptance-at">Customer acceptance timestamp</Label>
            <Input
              id="acceptance-at"
              type="datetime-local"
              value={acceptedAt}
              onChange={(event) => setAcceptedAt(event.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="acceptance-by">Accepted by (customer contact)</Label>
            <Input
              id="acceptance-by"
              value={acceptedBy}
              maxLength={160}
              onChange={(event) => setAcceptedBy(event.target.value)}
              placeholder="Name on the signed order"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="acceptance-reference">Evidence reference</Label>
            <Input
              id="acceptance-reference"
              value={reference}
              maxLength={500}
              onChange={(event) => setReference(event.target.value)}
              placeholder="Signed quote id, customer PO number, portal receipt"
            />
          </div>
          <div className="sm:col-span-2 space-y-1.5">
            <Label htmlFor="acceptance-notes">Notes (optional)</Label>
            <Textarea
              id="acceptance-notes"
              value={notes}
              maxLength={2000}
              onChange={(event) => setNotes(event.target.value)}
            />
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" size="sm" disabled={pending} onClick={() => void recordAndConvert()}>
          {pending ? (
            <Loader2 className="size-3.5 animate-spin" aria-hidden />
          ) : (
            <FileCheck2 className="size-3.5" aria-hidden />
          )}
          {pending
            ? "Converting…"
            : existing
              ? "Convert to sales order"
              : "Record acceptance and convert"}
        </Button>
        <span className="inline-flex items-center gap-1.5 text-[10.5px] text-mist-600">
          <AlertTriangle className="size-3 text-amber-400" aria-hidden />
          One transaction: the order, the WON transition and the audit rows commit together.
        </span>
      </div>
    </div>
  );
}
