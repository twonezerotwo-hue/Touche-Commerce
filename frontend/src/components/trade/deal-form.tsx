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
import { createDeal } from "@/lib/trade/client";
import { formatMoney, lineTotal, sumTotals } from "@/lib/trade/format";
import type { Counterparty, Product } from "@/lib/trade/types";

interface LineDraft {
  key: string;
  productId: string;
  quantity: string;
  unitPrice: string;
}

function newLine(product?: Product): LineDraft {
  return {
    key: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    productId: product?.id ?? "",
    quantity: "1.000",
    unitPrice: product?.unit_price ?? "",
  };
}

export function DealForm({
  counterparties,
  products,
  csrfToken,
  defaultCurrency,
}: {
  counterparties: readonly Counterparty[];
  products: readonly Product[];
  csrfToken: string;
  defaultCurrency: string;
}) {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [counterpartyId, setCounterpartyId] = useState(counterparties[0]?.id ?? "");
  const [currency, setCurrency] = useState(defaultCurrency);
  const [expectedCloseDate, setExpectedCloseDate] = useState("");
  const [notes, setNotes] = useState("");
  const [lines, setLines] = useState<LineDraft[]>([newLine(products[0])]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const productById = useMemo(
    () => new Map(products.map((product) => [product.id, product])),
    [products],
  );
  const total = sumTotals(lines.map((line) => lineTotal(line.quantity, line.unitPrice)));

  function updateLine(key: string, patch: Partial<LineDraft>): void {
    setLines((current) => current.map((line) => (line.key === key ? { ...line, ...patch } : line)));
  }

  function chooseProduct(key: string, productId: string): void {
    const product = productById.get(productId);
    updateLine(key, {
      productId,
      unitPrice: product ? product.unit_price : "",
    });
  }

  function addLine(): void {
    const used = new Set(lines.map((line) => line.productId));
    const next = products.find((product) => !used.has(product.id)) ?? products[0];
    setLines((current) => [...current, newLine(next)]);
  }

  function removeLine(key: string): void {
    setLines((current) => (current.length === 1 ? current : current.filter((l) => l.key !== key)));
  }

  async function submit(event: React.FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setError(null);

    if (!title.trim()) {
      setError("A deal title is required.");
      return;
    }
    if (!counterpartyId) {
      setError("Select a counterparty.");
      return;
    }
    const productIds = lines.map((line) => line.productId);
    if (new Set(productIds).size !== productIds.length) {
      setError("Each product may appear only once per deal.");
      return;
    }
    if (lines.some((line) => !line.productId)) {
      setError("Every line needs a product.");
      return;
    }
    if (lines.some((line) => !(Number.parseFloat(line.quantity) > 0))) {
      setError("Every line needs a quantity greater than zero.");
      return;
    }
    if (lines.some((line) => line.unitPrice === "" || Number.parseFloat(line.unitPrice) < 0)) {
      setError("Every line needs a non-negative unit price.");
      return;
    }

    setPending(true);
    const result = await createDeal(
      {
        title: title.trim(),
        counterparty_id: counterpartyId,
        currency: currency.trim().toUpperCase(),
        expected_close_date: expectedCloseDate || null,
        notes: notes.trim() || null,
        items: lines.map((line) => ({
          product_id: line.productId,
          quantity: line.quantity,
          unit_price: line.unitPrice,
        })),
      },
      csrfToken,
    );
    setPending(false);

    if (!result.ok) {
      setError(
        result.requestId ? `${result.message} (request ${result.requestId})` : result.message,
      );
      return;
    }
    router.push(`/deals/${result.data.id}`);
    router.refresh();
  }

  if (counterparties.length === 0 || products.length === 0) {
    return (
      <Alert variant="warning" title="Master data required">
        A deal needs at least one counterparty and one product. Create them in{" "}
        <span className="font-mono">/crm</span> and <span className="font-mono">/products</span>{" "}
        first.
      </Alert>
    );

    return (
      <form onSubmit={submit} className="space-y-5">
        {error ? <Alert variant="danger">{error}</Alert> : null}

        <section className="panel rounded-xl p-6">
          <span className="eyebrow">Deal header</span>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="deal-title">Title</Label>
              <Input
                id="deal-title"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder="50 MT aluminium ingots, Q4 shipment"
                maxLength={160}
                required
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="deal-counterparty">Counterparty</Label>
              <Select
                id="deal-counterparty"
                value={counterpartyId}
                onChange={(event) => setCounterpartyId(event.target.value)}
                required
              >
                {counterparties.map((counterparty) => (
                  <option key={counterparty.id} value={counterparty.id}>
                    {counterparty.name} · {counterparty.type}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="deal-currency">Currency</Label>
              <Input
                id="deal-currency"
                value={currency}
                onChange={(event) => setCurrency(event.target.value)}
                maxLength={3}
                required
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="deal-close-date">Expected close</Label>
              <Input
                id="deal-close-date"
                type="date"
                value={expectedCloseDate}
                onChange={(event) => setExpectedCloseDate(event.target.value)}
              />
            </div>
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="deal-notes">Notes</Label>
              <Textarea
                id="deal-notes"
                value={notes}
                onChange={(event) => setNotes(event.target.value)}
                maxLength={2000}
                placeholder="Incoterm, payment terms, logistics constraints…"
              />
            </div>
          </div>
        </section>

        <section className="panel rounded-xl p-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <span className="eyebrow">Lines</span>
              <p className="mt-1 text-[11.5px] text-mist-600">
                One line per product. Lines are immutable once the deal exists.
              </p>
            </div>
            <div className="text-right">
              <p className="text-[10px] uppercase tracking-[0.16em] text-mist-600">Deal value</p>
              <p className="font-display text-xl text-mist-100">{formatMoney(total, currency)}</p>
            </div>
          </div>

          <div className="mt-4 space-y-3">
            {lines.map((line, index) => {
              const product = productById.get(line.productId);
              return (
                <div
                  key={line.key}
                  className="grid gap-3 rounded-lg border border-white/[0.06] bg-white/[0.015] p-3 sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)_auto]"
                >
                  <div className="space-y-1.5">
                    <Label htmlFor={`line-product-${index}`}>Product</Label>
                    <Select
                      id={`line-product-${index}`}
                      value={line.productId}
                      onChange={(event) => chooseProduct(line.key, event.target.value)}
                    >
                      {products.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.sku} · {item.name}
                        </option>
                      ))}
                    </Select>
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor={`line-quantity-${index}`}>
                      Quantity {product ? `(${product.unit})` : ""}
                    </Label>
                    <Input
                      id={`line-quantity-${index}`}
                      value={line.quantity}
                      onChange={(event) => updateLine(line.key, { quantity: event.target.value })}
                      inputMode="decimal"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor={`line-price-${index}`}>Unit price</Label>
                    <Input
                      id={`line-price-${index}`}
                      value={line.unitPrice}
                      onChange={(event) => updateLine(line.key, { unitPrice: event.target.value })}
                      inputMode="decimal"
                    />
                  </div>
                  <div className="flex items-end justify-between gap-2 sm:flex-col sm:items-end">
                    <p className="text-[12px] text-mist-300">
                      {formatMoney(lineTotal(line.quantity, line.unitPrice), currency)}
                    </p>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      aria-label="Remove line"
                      onClick={() => removeLine(line.key)}
                      disabled={lines.length === 1}
                    >
                      <Trash2 className="size-4" aria-hidden />
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-2">
            <Button type="button" variant="outline" size="sm" onClick={addLine}>
              <Plus className="size-3.5" aria-hidden />
              Add line
            </Button>
            <p className="text-[11px] text-mist-600">
              Created as <span className="font-mono">DRAFT</span>; status changes go through the
              transition endpoint.
            </p>
          </div>
        </section>

        <div className="flex items-center gap-2">
          <Button type="submit" disabled={pending}>
            {pending ? <Loader2 className="size-4 animate-spin" aria-hidden /> : null}
            {pending ? "Creating…" : "Create deal"}
          </Button>
          <Button type="button" variant="ghost" onClick={() => router.back()}>
            Cancel
          </Button>
        </div>
      </form>
    );
  }
}
