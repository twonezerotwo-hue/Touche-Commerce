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
import { createSalesQuote } from "@/lib/sourcing/client";
import { INCOTERMS, type PricingScenario, type SalesQuoteCreate } from "@/lib/sourcing/types";
import type { Counterparty } from "@/lib/trade/types";

/** Draft a customer quotation from a stored pricing scenario. */
export function SalesQuoteForm({
  scenario,
  buyers,
  csrfToken,
}: {
  scenario: PricingScenario;
  buyers: readonly Counterparty[];
  csrfToken: string;
}) {
  const router = useRouter();
  const [customerId, setCustomerId] = useState(buyers[0]?.id ?? "");
  const [validUntil, setValidUntil] = useState("");
  const [incoterm, setIncoterm] = useState<SalesQuoteCreate["incoterm"]>(
    scenario.sales_incoterm ?? "CIF",
  );
  const [place, setPlace] = useState(scenario.sales_named_place ?? "");
  const [paymentTerms, setPaymentTerms] = useState("30 days net");
  const [notes, setNotes] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setError(null);

    if (!customerId) {
      setError("Select the customer this quote is for.");
      return;
    }
    if (!validUntil) {
      setError("A validity date is required.");
      return;
    }

    const payload: SalesQuoteCreate = {
      scenario_id: scenario.id,
      customer_id: customerId,
      valid_until: validUntil,
      incoterm: incoterm as SalesQuoteCreate["incoterm"],
      named_delivery_place: place.trim(),
      payment_terms: paymentTerms.trim(),
      notes: notes.trim() || null,
    };

    setPending(true);
    const result = await createSalesQuote(payload, csrfToken);
    setPending(false);

    if (!result.ok) {
      setError(
        result.requestId ? `${result.message} (request ${result.requestId})` : result.message,
      );
      return;
    }

    router.push(`/sales-quotes/${result.data.id}`);
    router.refresh();
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      {error ? <Alert variant="danger">{error}</Alert> : null}

      <div className="grid gap-3 sm:grid-cols-3">
        <div className="space-y-1.5">
          <Label htmlFor="sq-customer">Customer</Label>
          <Select
            id="sq-customer"
            value={customerId}
            onChange={(event) => setCustomerId(event.target.value)}
          >
            {buyers.length === 0 ? <option value="">No buyers in CRM</option> : null}
            {buyers.map((buyer) => (
              <option key={buyer.id} value={buyer.id}>
                {buyer.name}
              </option>
            ))}
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="sq-valid">Valid until</Label>
          <Input
            id="sq-valid"
            type="date"
            value={validUntil}
            onChange={(event) => setValidUntil(event.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="sq-incoterm">Incoterm</Label>
          <Select
            id="sq-incoterm"
            value={incoterm}
            onChange={(event) => setIncoterm(event.target.value as SalesQuoteCreate["incoterm"])}
          >
            {INCOTERMS.map((term) => (
              <option key={term} value={term}>
                {term}
              </option>
            ))}
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="sq-place">Named place</Label>
          <Input
            id="sq-place"
            value={place}
            maxLength={160}
            onChange={(event) => setPlace(event.target.value)}
            placeholder="Rotterdam, NL"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="sq-payment">Payment terms</Label>
          <Input
            id="sq-payment"
            value={paymentTerms}
            maxLength={200}
            onChange={(event) => setPaymentTerms(event.target.value)}
          />
        </div>
        <div className="space-y-1.5 sm:col-span-3">
          <Label htmlFor="sq-notes">Notes</Label>
          <Textarea
            id="sq-notes"
            value={notes}
            maxLength={2000}
            onChange={(event) => setNotes(event.target.value)}
          />
        </div>
      </div>

      <div className="flex items-center gap-2">
        <Button type="submit" size="sm" disabled={pending}>
          {pending ? <Loader2 className="size-3.5 animate-spin" aria-hidden /> : null}
          {pending ? "Drafting…" : "Draft sales quote"}
        </Button>
        <p className="text-[11px] text-mist-600">
          Prices are copied from the scenario results. Approval needs verified inputs and a second
          person with finance.approve.
        </p>
      </div>
    </form>
  );
}
