"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Loader2 } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { recordSupplierQuote } from "@/lib/sourcing/client";
import { INCOTERMS, type Rfq, type SupplierQuoteCreate } from "@/lib/sourcing/types";
import { formatQuantity } from "@/lib/trade/format";

/**
 * Record a supplier's reply against an RFQ.
 *
 * Prices are typed exactly as the supplier wrote them; the line description and
 * unit are inherited from the RFQ, so a quote can never quietly rename a product.
 */
export function QuoteForm({
  rfq,
  csrfToken,
  defaultCurrency,
}: {
  rfq: Rfq;
  csrfToken: string;
  defaultCurrency: string;
}) {
  const router = useRouter();
  const [currency, setCurrency] = useState(defaultCurrency);
  const [incoterm, setIncoterm] = useState("CIF");
  const [place, setPlace] = useState(rfq.delivery_location);
  const [paymentTerms, setPaymentTerms] = useState("30 days net");
  const [leadTime, setLeadTime] = useState("21");
  const [validUntil, setValidUntil] = useState("");
  const [sourceReference, setSourceReference] = useState("");
  const [supplierReference, setSupplierReference] = useState("");
  const [notes, setNotes] = useState("");
  const [prices, setPrices] = useState<Record<string, string>>(
    Object.fromEntries(rfq.items.map((item) => [item.product_id, ""])),
  );
  const [moqs, setMoqs] = useState<Record<string, string>>({});
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setError(null);

    if (!validUntil) {
      setError("The quote validity date is required.");
      return;
    }
    if (sourceReference.trim().length < 3) {
      setError("Record where the quote came from (email, file or portal message).");
      return;
    }
    const items = rfq.items
      .filter((item) => (prices[item.product_id] ?? "").trim() !== "")
      .map((item) => ({
        product_id: item.product_id,
        quantity: item.quantity,
        unit_price: prices[item.product_id].trim(),
        moq: (moqs[item.product_id] ?? "").trim() || null,
      }));
    if (items.length === 0) {
      setError("Enter a unit price for at least one line.");
      return;
    }

    const payload: SupplierQuoteCreate = {
      currency: currency.toUpperCase(),
      incoterm: incoterm as SupplierQuoteCreate["incoterm"],
      named_delivery_place: place.trim(),
      payment_terms: paymentTerms.trim(),
      lead_time_days: Number.parseInt(leadTime, 10) || 0,
      valid_until: validUntil,
      source_reference: sourceReference.trim(),
      supplier_reference: supplierReference.trim() || null,
      notes: notes.trim() || null,
      items,
    };

    setPending(true);
    const result = await recordSupplierQuote(rfq.id, payload, csrfToken);
    setPending(false);

    if (!result.ok) {
      setError(
        result.requestId ? `${result.message} (request ${result.requestId})` : result.message,
      );
      return;
    }

    setPrices(Object.fromEntries(rfq.items.map((item) => [item.product_id, ""])));
    setMoqs({});
    setNotes("");
    router.refresh();
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      {error ? <Alert variant="danger">{error}</Alert> : null}

      <div className="grid gap-3 sm:grid-cols-3">
        <div className="space-y-1.5">
          <Label htmlFor="quote-currency">Currency</Label>
          <Input
            id="quote-currency"
            value={currency}
            maxLength={3}
            onChange={(event) => setCurrency(event.target.value.toUpperCase())}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="quote-incoterm">Incoterm</Label>
          <Select
            id="quote-incoterm"
            value={incoterm}
            onChange={(event) => setIncoterm(event.target.value)}
          >
            {INCOTERMS.map((term) => (
              <option key={term} value={term}>
                {term}
              </option>
            ))}
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="quote-place">Named place</Label>
          <Input
            id="quote-place"
            value={place}
            maxLength={160}
            onChange={(event) => setPlace(event.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="quote-payment">Payment terms</Label>
          <Input
            id="quote-payment"
            value={paymentTerms}
            maxLength={200}
            onChange={(event) => setPaymentTerms(event.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="quote-lead">Lead time (days)</Label>
          <Input
            id="quote-lead"
            value={leadTime}
            inputMode="numeric"
            onChange={(event) => setLeadTime(event.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="quote-valid">Valid until</Label>
          <Input
            id="quote-valid"
            type="date"
            value={validUntil}
            onChange={(event) => setValidUntil(event.target.value)}
          />
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor="quote-source">Source (required)</Label>
          <Input
            id="quote-source"
            value={sourceReference}
            maxLength={200}
            onChange={(event) => setSourceReference(event.target.value)}
            placeholder="email: quote 2026-10-22 from Supplier One"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="quote-supplier-ref">Supplier reference</Label>
          <Input
            id="quote-supplier-ref"
            value={supplierReference}
            maxLength={80}
            onChange={(event) => setSupplierReference(event.target.value)}
          />
        </div>
        <div className="space-y-1.5 sm:col-span-3">
          <Label htmlFor="quote-notes">Notes</Label>
          <Textarea
            id="quote-notes"
            value={notes}
            maxLength={2000}
            onChange={(event) => setNotes(event.target.value)}
          />
        </div>
      </div>

      <div className="space-y-2">
        {rfq.items.map((item) => (
          <div key={item.id} className="grid gap-2 sm:grid-cols-[2fr_1fr_1fr]">
            <div className="text-[12px] leading-snug text-mist-200">
              <span className="font-mono text-[11px] text-mist-500">{item.sku}</span>{" "}
              {item.description}
              <span className="ml-1 text-mist-600">
                ({formatQuantity(item.quantity, item.unit)} requested)
              </span>
            </div>
            <Input
              aria-label={`Unit price for ${item.sku}`}
              value={prices[item.product_id] ?? ""}
              inputMode="decimal"
              placeholder="Unit price"
              onChange={(event) =>
                setPrices((current) => ({ ...current, [item.product_id]: event.target.value }))
              }
            />
            <Input
              aria-label={`MOQ for ${item.sku}`}
              value={moqs[item.product_id] ?? ""}
              inputMode="decimal"
              placeholder="MOQ (optional)"
              onChange={(event) =>
                setMoqs((current) => ({ ...current, [item.product_id]: event.target.value }))
              }
            />
          </div>
        ))}
      </div>

      <div className="flex items-center gap-2">
        <Button type="submit" size="sm" disabled={pending}>
          {pending ? <Loader2 className="size-3.5 animate-spin" aria-hidden /> : null}
          {pending ? "Recording…" : "Record quote"}
        </Button>
        <p className="text-[11px] text-mist-600">
          Only lines with a price are quoted. The RFQ moves to RESPONDED.
        </p>
      </div>
    </form>
  );
}
