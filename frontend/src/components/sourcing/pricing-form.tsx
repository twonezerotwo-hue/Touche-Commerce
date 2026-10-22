"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { Loader2, Plus, Trash2 } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { createPricingScenario } from "@/lib/sourcing/client";
import {
  COST_TYPES,
  type FxRate,
  type PricingComponentRequest,
  type PricingScenarioRequest,
  type SupplierQuote,
} from "@/lib/sourcing/types";

interface ComponentDraft {
  key: string;
  costType: (typeof COST_TYPES)[number];
  amount: string;
  currency: string;
  basis: "ORDER" | "LINE";
  productId: string;
  sourceReference: string;
  verification: "ESTIMATED" | "VERIFIED";
  fxRateId: string;
}

function newComponent(currency: string): ComponentDraft {
  return {
    key: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    costType: "FREIGHT",
    amount: "",
    currency,
    basis: "ORDER",
    productId: "",
    sourceReference: "",
    verification: "ESTIMATED",
    fxRateId: "",
  };
}

/**
 * Price a supplier quote.
 *
 * FX is chosen from recorded snapshots only: there is no "use today's rate"
 * option, because a landed cost that cannot be reproduced is not a quote input.
 */
export function PricingForm({
  quote,
  fxRates,
  csrfToken,
}: {
  quote: SupplierQuote;
  fxRates: readonly FxRate[];
  csrfToken: string;
}) {
  const router = useRouter();
  const [targetCurrency, setTargetCurrency] = useState(quote.currency);
  const [method, setMethod] = useState<"margin" | "markup" | "none">("margin");
  const [percent, setPercent] = useState("20");
  const [fxRateId, setFxRateId] = useState("");
  const [components, setComponents] = useState<ComponentDraft[]>([newComponent(quote.currency)]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const conversionNeeded = targetCurrency.toUpperCase() !== quote.currency;
  const quoteFx = useMemo(
    () =>
      fxRates.filter(
        (rate) =>
          rate.base_currency === quote.currency &&
          rate.quote_currency === targetCurrency.toUpperCase(),
      ),
    [fxRates, quote.currency, targetCurrency],
  );

  function update(key: string, patch: Partial<ComponentDraft>): void {
    setComponents((current) =>
      current.map((component) => (component.key === key ? { ...component, ...patch } : component)),
    );
  }

  function componentPayload(component: ComponentDraft): PricingComponentRequest {
    const needsFx = component.currency.toUpperCase() !== targetCurrency.toUpperCase();
    return {
      cost_type: component.costType,
      amount: component.amount.trim() || "0",
      currency: component.currency.toUpperCase(),
      basis: component.basis,
      source_reference: component.sourceReference.trim(),
      verification_status: component.verification,
      fx_rate_snapshot_id: needsFx ? component.fxRateId || null : null,
      product_id: component.basis === "LINE" ? component.productId || null : null,
      notes: null,
    };
  }

  async function submit(event: React.FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setError(null);

    if (conversionNeeded && !fxRateId) {
      setError(`Select a recorded ${quote.currency}/${targetCurrency.toUpperCase()} snapshot.`);
      return;
    }
    if (components.some((component) => component.sourceReference.trim().length < 3)) {
      setError("Every cost component needs a source reference of at least 3 characters.");
      return;
    }
    if (components.some((component) => component.basis === "LINE" && !component.productId)) {
      setError("A LINE cost must name the product it belongs to.");
      return;
    }
    if (
      components.some(
        (component) =>
          component.currency.toUpperCase() !== targetCurrency.toUpperCase() && !component.fxRateId,
      )
    ) {
      setError("A cost component in another currency needs its own FX snapshot.");
      return;
    }

    const payload: PricingScenarioRequest = {
      supplier_quote_id: quote.id,
      target_currency: targetCurrency.toUpperCase(),
      margin_pct: method === "margin" ? percent : "0",
      markup_pct: method === "markup" ? percent : "0",
      fx_rate_snapshot_id: conversionNeeded ? fxRateId : null,
      components: components.map(componentPayload),
    };

    setPending(true);
    const result = await createPricingScenario(payload, csrfToken);
    setPending(false);

    if (!result.ok) {
      setError(
        result.requestId ? `${result.message} (request ${result.requestId})` : result.message,
      );
      return;
    }

    router.push(`/pricing/${result.data.id}`);
    router.refresh();
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      {error ? <Alert variant="danger">{error}</Alert> : null}

      <div className="grid gap-3 sm:grid-cols-4">
        <div className="space-y-1.5">
          <Label htmlFor="pricing-target">Target currency</Label>
          <Input
            id="pricing-target"
            value={targetCurrency}
            maxLength={3}
            onChange={(event) => {
              setTargetCurrency(event.target.value.toUpperCase());
              setFxRateId("");
            }}
          />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="pricing-method">Pricing method</Label>
          <Select
            id="pricing-method"
            value={method}
            onChange={(event) => setMethod(event.target.value as typeof method)}
          >
            <option value="margin">Margin on price</option>
            <option value="markup">Markup on cost</option>
            <option value="none">Pass through at cost</option>
          </Select>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="pricing-percent">Percent</Label>
          <Input
            id="pricing-percent"
            value={percent}
            inputMode="decimal"
            disabled={method === "none"}
            onChange={(event) => setPercent(event.target.value)}
          />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="pricing-fx">Quote FX snapshot</Label>
          <Select
            id="pricing-fx"
            value={fxRateId}
            disabled={!conversionNeeded}
            onChange={(event) => setFxRateId(event.target.value)}
          >
            <option value="">
              {conversionNeeded ? "Select a recorded rate" : "Same currency — not needed"}
            </option>
            {quoteFx.map((rate) => (
              <option key={rate.id} value={rate.id}>
                {rate.base_currency}/{rate.quote_currency} @ {rate.rate} ({rate.source})
              </option>
            ))}
          </Select>
        </div>
      </div>

      {conversionNeeded && quoteFx.length === 0 ? (
        <Alert variant="info" title="No matching FX snapshot">
          Record a {quote.currency}/{targetCurrency.toUpperCase()} rate on the FX page first.
          Pricing never infers a rate.
        </Alert>
      ) : null}

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <h3 className="text-[12.5px] font-medium text-mist-100">Cost components</h3>
          <Button
            type="button"
            size="sm"
            variant="subtle"
            onClick={() =>
              setComponents((current) => [...current, newComponent(targetCurrency.toUpperCase())])
            }
          >
            <Plus className="size-3.5" aria-hidden />
            Add cost
          </Button>
        </div>

        {components.length === 0 ? (
          <p className="text-[11.5px] text-mist-600">
            No additional costs: the landed cost is the converted purchase value.
          </p>
        ) : null}

        {components.map((component) => {
          const needsFx = component.currency.toUpperCase() !== targetCurrency.toUpperCase();
          const componentFx = fxRates.filter(
            (rate) =>
              rate.base_currency === component.currency.toUpperCase() &&
              rate.quote_currency === targetCurrency.toUpperCase(),
          );
          return (
            <div
              key={component.key}
              className="grid gap-2 rounded-lg border border-white/[0.06] p-3 sm:grid-cols-3"
            >
              <div className="space-y-1">
                <Label>Type</Label>
                <Select
                  aria-label="Cost type"
                  value={component.costType}
                  onChange={(event) =>
                    update(component.key, {
                      costType: event.target.value as ComponentDraft["costType"],
                    })
                  }
                >
                  {COST_TYPES.map((type) => (
                    <option key={type} value={type}>
                      {type.replaceAll("_", " ")}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="space-y-1">
                <Label>Amount</Label>
                <Input
                  aria-label="Amount"
                  value={component.amount}
                  inputMode="decimal"
                  onChange={(event) => update(component.key, { amount: event.target.value })}
                />
              </div>
              <div className="space-y-1">
                <Label>Currency</Label>
                <Input
                  aria-label="Component currency"
                  value={component.currency}
                  maxLength={3}
                  onChange={(event) =>
                    update(component.key, { currency: event.target.value.toUpperCase() })
                  }
                />
              </div>
              <div className="space-y-1">
                <Label>Basis</Label>
                <Select
                  aria-label="Cost basis"
                  value={component.basis}
                  onChange={(event) =>
                    update(component.key, {
                      basis: event.target.value as ComponentDraft["basis"],
                    })
                  }
                >
                  <option value="ORDER">Whole order (pro-rata)</option>
                  <option value="LINE">One product line</option>
                </Select>
              </div>
              <div className="space-y-1">
                <Label>Product</Label>
                <Select
                  aria-label="Cost product"
                  value={component.productId}
                  disabled={component.basis !== "LINE"}
                  onChange={(event) => update(component.key, { productId: event.target.value })}
                >
                  <option value="">{component.basis === "LINE" ? "Select…" : "—"}</option>
                  {quote.items.map((item) => (
                    <option key={item.id} value={item.product_id}>
                      {item.sku}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="space-y-1">
                <Label>Verification</Label>
                <Select
                  aria-label="Verification"
                  value={component.verification}
                  onChange={(event) =>
                    update(component.key, {
                      verification: event.target.value as ComponentDraft["verification"],
                    })
                  }
                >
                  <option value="ESTIMATED">Estimated</option>
                  <option value="VERIFIED">Verified</option>
                </Select>
              </div>

              <div className="space-y-1 sm:col-span-2">
                <Label>Source reference</Label>
                <Input
                  aria-label="Source reference"
                  value={component.sourceReference}
                  onChange={(event) =>
                    update(component.key, { sourceReference: event.target.value })
                  }
                  placeholder="Freight invoice number"
                />
              </div>
              <div className="space-y-1">
                <Label>Component FX</Label>
                <Select
                  aria-label="Component FX snapshot"
                  value={component.fxRateId}
                  disabled={!needsFx}
                  onChange={(event) => update(component.key, { fxRateId: event.target.value })}
                >
                  <option value="">{needsFx ? "Select…" : "Not needed"}</option>
                  {componentFx.map((rate) => (
                    <option key={rate.id} value={rate.id}>
                      {rate.base_currency}/{rate.quote_currency} @ {rate.rate}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="flex items-end sm:col-span-3">
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() =>
                    setComponents((current) => current.filter((item) => item.key !== component.key))
                  }
                >
                  <Trash2 className="size-3.5" aria-hidden />
                  Remove
                </Button>
              </div>
            </div>
          );
        })}
      </div>

      <div className="flex items-center gap-2">
        <Button type="submit" size="sm" disabled={pending}>
          {pending ? <Loader2 className="size-3.5 animate-spin" aria-hidden /> : null}
          {pending ? "Calculating…" : "Calculate landed cost"}
        </Button>
        <p className="text-[11px] text-mist-600">
          Results are stored with their inputs so the price can be reproduced later.
        </p>
      </div>
    </form>
  );
}
