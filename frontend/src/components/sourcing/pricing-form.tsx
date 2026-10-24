"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { Loader2, Plus, Trash2 } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { useLocale } from "@/lib/i18n/locale-provider";
import { costTypeText } from "@/lib/i18n/value-labels";
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
  const { t } = useLocale();
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
      setError(
        t("pfSelectSnapshot", { pair: `${quote.currency}/${targetCurrency.toUpperCase()}` }),
      );
      return;
    }
    if (components.some((component) => component.sourceReference.trim().length < 3)) {
      setError(t("pfSourceRefShort"));
      return;
    }
    if (components.some((component) => component.basis === "LINE" && !component.productId)) {
      setError(t("pfLineNeedsProduct"));
      return;
    }
    if (
      components.some(
        (component) =>
          component.currency.toUpperCase() !== targetCurrency.toUpperCase() && !component.fxRateId,
      )
    ) {
      setError(t("pfComponentNeedsFx"));
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
        result.requestId
          ? t("srcErrWithRequest", { message: result.message, id: result.requestId })
          : result.message,
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
          <Label htmlFor="pricing-target">{t("pfTargetCurrency")}</Label>
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
          <Label htmlFor="pricing-method">{t("pfMethod")}</Label>
          <Select
            id="pricing-method"
            value={method}
            onChange={(event) => setMethod(event.target.value as typeof method)}
          >
            <option value="margin">{t("pfMethodMargin")}</option>
            <option value="markup">{t("pfMethodMarkup")}</option>
            <option value="none">{t("pfMethodNone")}</option>
          </Select>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="pricing-percent">{t("pfPercent")}</Label>
          <Input
            id="pricing-percent"
            value={percent}
            inputMode="decimal"
            disabled={method === "none"}
            onChange={(event) => setPercent(event.target.value)}
          />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="pricing-fx">{t("pfQuoteFx")}</Label>
          <Select
            id="pricing-fx"
            value={fxRateId}
            disabled={!conversionNeeded}
            onChange={(event) => setFxRateId(event.target.value)}
          >
            <option value="">{conversionNeeded ? t("pfSelectRate") : t("pfSameCurrency")}</option>
            {quoteFx.map((rate) => (
              <option key={rate.id} value={rate.id}>
                {rate.base_currency}/{rate.quote_currency} @ {rate.rate} ({rate.source})
              </option>
            ))}
          </Select>
        </div>
      </div>

      {conversionNeeded && quoteFx.length === 0 ? (
        <Alert variant="info" title={t("pfNoSnapshotTitle")}>
          {t("pfNoSnapshotBody", { pair: `${quote.currency}/${targetCurrency.toUpperCase()}` })}
        </Alert>
      ) : null}

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <h3 className="text-[12.5px] font-medium text-mist-100">{t("prcCostComponents")}</h3>
          <Button
            type="button"
            size="sm"
            variant="subtle"
            onClick={() =>
              setComponents((current) => [...current, newComponent(targetCurrency.toUpperCase())])
            }
          >
            <Plus className="size-3.5" aria-hidden />
            {t("pfAddCost")}
          </Button>
        </div>

        {components.length === 0 ? (
          <p className="text-[11.5px] text-mist-600">{t("pfNoCosts")}</p>
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
                <Label>{t("srcColType")}</Label>
                <Select
                  aria-label={t("pfCostType")}
                  value={component.costType}
                  onChange={(event) =>
                    update(component.key, {
                      costType: event.target.value as ComponentDraft["costType"],
                    })
                  }
                >
                  {COST_TYPES.map((type) => (
                    <option key={type} value={type}>
                      {costTypeText(t, type)}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="space-y-1">
                <Label>{t("srcColAmount")}</Label>
                <Input
                  aria-label={t("srcColAmount")}
                  value={component.amount}
                  inputMode="decimal"
                  onChange={(event) => update(component.key, { amount: event.target.value })}
                />
              </div>
              <div className="space-y-1">
                <Label>{t("columnCurrency")}</Label>
                <Input
                  aria-label={t("pfComponentCurrency")}
                  value={component.currency}
                  maxLength={3}
                  onChange={(event) =>
                    update(component.key, { currency: event.target.value.toUpperCase() })
                  }
                />
              </div>
              <div className="space-y-1">
                <Label>{t("srcColBasis")}</Label>
                <Select
                  aria-label={t("pfCostBasis")}
                  value={component.basis}
                  onChange={(event) =>
                    update(component.key, {
                      basis: event.target.value as ComponentDraft["basis"],
                    })
                  }
                >
                  <option value="ORDER">{t("prcBasisOrder")}</option>
                  <option value="LINE">{t("prcBasisLine")}</option>
                </Select>
              </div>
              <div className="space-y-1">
                <Label>{t("pfProduct")}</Label>
                <Select
                  aria-label={t("pfCostProduct")}
                  value={component.productId}
                  disabled={component.basis !== "LINE"}
                  onChange={(event) => update(component.key, { productId: event.target.value })}
                >
                  <option value="">{component.basis === "LINE" ? t("srcSelect") : "—"}</option>
                  {quote.items.map((item) => (
                    <option key={item.id} value={item.product_id}>
                      {item.sku}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="space-y-1">
                <Label>{t("srcColVerification")}</Label>
                <Select
                  aria-label={t("srcColVerification")}
                  value={component.verification}
                  onChange={(event) =>
                    update(component.key, {
                      verification: event.target.value as ComponentDraft["verification"],
                    })
                  }
                >
                  <option value="ESTIMATED">{t("prcEstimated")}</option>
                  <option value="VERIFIED">{t("prcVerified")}</option>
                </Select>
              </div>

              <div className="space-y-1 sm:col-span-2">
                <Label>{t("suqSourceRef")}</Label>
                <Input
                  aria-label={t("suqSourceRef")}
                  value={component.sourceReference}
                  onChange={(event) =>
                    update(component.key, { sourceReference: event.target.value })
                  }
                  placeholder={t("pfSourcePlaceholder")}
                />
              </div>
              <div className="space-y-1">
                <Label>{t("pfComponentFx")}</Label>
                <Select
                  aria-label={t("pfComponentFxSnapshot")}
                  value={component.fxRateId}
                  disabled={!needsFx}
                  onChange={(event) => update(component.key, { fxRateId: event.target.value })}
                >
                  <option value="">{needsFx ? t("srcSelect") : t("pfNotNeeded")}</option>
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
                  {t("pfRemove")}
                </Button>
              </div>
            </div>
          );
        })}
      </div>

      <div className="flex items-center gap-2">
        <Button type="submit" size="sm" disabled={pending}>
          {pending ? <Loader2 className="size-3.5 animate-spin" aria-hidden /> : null}
          {pending ? t("pfCalculating") : t("pfCalculate")}
        </Button>
        <p className="text-[11px] text-mist-600">{t("pfHint")}</p>
      </div>
    </form>
  );
}
