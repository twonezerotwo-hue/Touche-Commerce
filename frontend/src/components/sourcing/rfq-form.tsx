"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { Loader2, Plus, Trash2 } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useLocale } from "@/lib/i18n/locale-provider";
import { createRfqs } from "@/lib/sourcing/client";
import type { RfqCreate } from "@/lib/sourcing/types";
import type { Counterparty, DealSummary, Product } from "@/lib/trade/types";

interface LineDraft {
  key: string;
  productId: string;
  description: string;
  quantity: string;
}

function newLine(product?: Product): LineDraft {
  return {
    key: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    productId: product?.id ?? "",
    description: product?.name ?? "",
    quantity: "1.000",
  };
}

/**
 * Create one RFQ per selected supplier.
 *
 * The backend writes all RFQs and their lines in a single transaction, so either
 * every supplier is asked or none is — a half-sent comparison would be worse than
 * a retry.
 */
export function RfqForm({
  deals,
  suppliers,
  products,
  csrfToken,
  defaultCurrency,
}: {
  deals: readonly DealSummary[];
  suppliers: readonly Counterparty[];
  products: readonly Product[];
  csrfToken: string;
  defaultCurrency: string;
}) {
  const router = useRouter();
  const { t } = useLocale();
  const [dealId, setDealId] = useState(deals[0]?.id ?? "");
  const [supplierIds, setSupplierIds] = useState<string[]>([]);
  const [currency, setCurrency] = useState(defaultCurrency);
  const [deliveryLocation, setDeliveryLocation] = useState("");
  const [deliveryTerms, setDeliveryTerms] = useState("CIF");
  const [dueDate, setDueDate] = useState("");
  const [notes, setNotes] = useState("");
  const [lines, setLines] = useState<LineDraft[]>([newLine(products[0])]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const productById = useMemo(
    () => new Map(products.map((product) => [product.id, product])),
    [products],
  );

  function toggleSupplier(id: string): void {
    setSupplierIds((current) =>
      current.includes(id) ? current.filter((value) => value !== id) : [...current, id],
    );
  }

  function updateLine(key: string, patch: Partial<LineDraft>): void {
    setLines((current) => current.map((line) => (line.key === key ? { ...line, ...patch } : line)));
  }

  function chooseProduct(key: string, productId: string): void {
    const product = productById.get(productId);
    updateLine(key, { productId, description: product?.name ?? "" });
  }

  async function submit(event: React.FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setError(null);

    if (!dealId) {
      setError(t("rfqfSelectDeal"));
      return;
    }
    if (supplierIds.length === 0) {
      setError(t("rfqfSelectSupplier"));
      return;
    }
    if (deliveryLocation.trim().length < 2) {
      setError(t("rfqfLocationRequired"));
      return;
    }
    if (lines.some((line) => !line.productId || !line.description.trim())) {
      setError(t("rfqfLineIncomplete"));
      return;
    }

    const payload: RfqCreate = {
      deal_id: dealId,
      supplier_ids: supplierIds,
      requested_currency: currency.toUpperCase(),
      requested_delivery_terms: deliveryTerms || null,
      delivery_location: deliveryLocation.trim(),
      response_due_date: dueDate || null,
      notes: notes.trim() || null,
      items: lines.map((line) => ({
        product_id: line.productId,
        description: line.description.trim(),
        quantity: line.quantity,
        unit: productById.get(line.productId)?.unit ?? "kg",
      })),
    };

    setPending(true);
    const result = await createRfqs(payload, csrfToken);
    setPending(false);

    if (!result.ok) {
      setError(
        result.requestId
          ? t("srcErrWithRequest", { message: result.message, id: result.requestId })
          : result.message,
      );
      return;
    }

    const created = result.data.items;
    router.push(created.length === 1 ? `/rfq/${created[0].id}` : "/rfq");
    router.refresh();
  }

  return (
    <form onSubmit={submit} className="space-y-5">
      {error ? <Alert variant="danger">{error}</Alert> : null}

      <div className="panel space-y-4 p-4">
        <h2 className="text-[13px] font-medium text-mist-100">{t("rfqfRequest")}</h2>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="rfq-deal">{t("rfqfDeal")}</Label>
            <Select
              id="rfq-deal"
              value={dealId}
              onChange={(event) => setDealId(event.target.value)}
            >
              {deals.length === 0 ? <option value="">{t("rfqfNoDeals")}</option> : null}
              {deals.map((deal) => (
                <option key={deal.id} value={deal.id}>
                  {deal.reference} · {deal.title}
                </option>
              ))}
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="rfq-currency">{t("rfqfCurrency")}</Label>
            <Input
              id="rfq-currency"
              value={currency}
              maxLength={3}
              onChange={(event) => setCurrency(event.target.value.toUpperCase())}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="rfq-location">{t("rfqfLocation")}</Label>
            <Input
              id="rfq-location"
              value={deliveryLocation}
              maxLength={160}
              onChange={(event) => setDeliveryLocation(event.target.value)}
              placeholder="Rotterdam, NL"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="rfq-terms">{t("rfqfTerms")}</Label>
            <Select
              id="rfq-terms"
              value={deliveryTerms}
              onChange={(event) => setDeliveryTerms(event.target.value)}
            >
              <option value="">{t("rfqfNotSpecified")}</option>
              {["EXW", "FCA", "FOB", "CFR", "CIF", "CPT", "CIP", "DAP", "DDP"].map((term) => (
                <option key={term} value={term}>
                  {term}
                </option>
              ))}
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="rfq-due">{t("rfqfDue")}</Label>
            <Input
              id="rfq-due"
              type="date"
              value={dueDate}
              onChange={(event) => setDueDate(event.target.value)}
            />
          </div>

          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="rfq-notes">{t("srcNotes")}</Label>
            <Textarea
              id="rfq-notes"
              value={notes}
              maxLength={2000}
              onChange={(event) => setNotes(event.target.value)}
              placeholder={t("rfqfNotesPlaceholder")}
            />
          </div>
        </div>
      </div>

      <div className="panel space-y-3 p-4">
        <h2 className="text-[13px] font-medium text-mist-100">{t("rfqfSuppliers")}</h2>
        <p className="text-[11px] text-mist-600">{t("rfqfSuppliersHint")}</p>
        {suppliers.length === 0 ? (
          <Alert variant="info" title={t("rfqfNoSuppliers")}>
            {t("rfqfNoSuppliersBody")}
          </Alert>
        ) : (
          <div className="flex flex-wrap gap-2">
            {suppliers.map((supplier) => {
              const selected = supplierIds.includes(supplier.id);
              return (
                <Button
                  key={supplier.id}
                  type="button"
                  size="sm"
                  variant={selected ? "default" : "outline"}
                  aria-pressed={selected}
                  onClick={() => toggleSupplier(supplier.id)}
                >
                  {supplier.name}
                </Button>
              );
            })}
          </div>
        )}
      </div>

      <div className="panel space-y-3 p-4">
        <div className="flex items-center justify-between">
          <h2 className="text-[13px] font-medium text-mist-100">{t("rfqfLines")}</h2>
          <Button
            type="button"
            size="sm"
            variant="subtle"
            onClick={() => {
              const used = new Set(lines.map((line) => line.productId));
              const next = products.find((product) => !used.has(product.id)) ?? products[0];
              setLines((current) => [...current, newLine(next)]);
            }}
            disabled={products.length === 0}
          >
            <Plus className="size-3.5" aria-hidden />
            {t("rfqfAddLine")}
          </Button>
        </div>

        <div className="space-y-2">
          {lines.map((line, index) => (
            <div key={line.key} className="grid gap-2 sm:grid-cols-[1.4fr_2fr_0.7fr_auto]">
              <Select
                aria-label={t("rfqfLineProduct", { n: index + 1 })}
                value={line.productId}
                onChange={(event) => chooseProduct(line.key, event.target.value)}
              >
                {products.map((product) => (
                  <option key={product.id} value={product.id}>
                    {product.sku}
                  </option>
                ))}
              </Select>
              <Input
                aria-label={t("rfqfLineDescription", { n: index + 1 })}
                value={line.description}
                maxLength={500}
                onChange={(event) => updateLine(line.key, { description: event.target.value })}
              />
              <Input
                aria-label={t("rfqfLineQuantity", { n: index + 1 })}
                value={line.quantity}
                inputMode="decimal"
                onChange={(event) => updateLine(line.key, { quantity: event.target.value })}
              />
              <Button
                type="button"
                size="iconSm"
                variant="ghost"
                aria-label={t("rfqfRemoveLine", { n: index + 1 })}
                disabled={lines.length === 1}
                onClick={() =>
                  setLines((current) => current.filter((item) => item.key !== line.key))
                }
              >
                <Trash2 className="size-3.5" aria-hidden />
              </Button>
            </div>
          ))}
        </div>
      </div>

      <div className="flex items-center gap-2">
        <Button type="submit" size="sm" disabled={pending}>
          {pending ? <Loader2 className="size-3.5 animate-spin" aria-hidden /> : null}
          {pending ? t("rfqfCreating") : t("rfqfCreate")}
        </Button>
        <p className="text-[11px] text-mist-600">{t("rfqfCreateHint")}</p>
      </div>
    </form>
  );
}
