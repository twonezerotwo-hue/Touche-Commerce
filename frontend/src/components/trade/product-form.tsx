"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Loader2, Plus, X } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { createProduct } from "@/lib/trade/client";
import { PRODUCT_UNITS } from "@/lib/trade/types";

const EMPTY = {
  sku: "",
  name: "",
  unit: "mt",
  currency: "USD",
  unit_price: "",
};

export function ProductForm({ csrfToken, canWrite }: { csrfToken: string; canWrite: boolean }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [values, setValues] = useState({ ...EMPTY });
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  if (!canWrite) {
    return (
      <Alert variant="info" title="Read-only access">
        Adding a product requires <span className="font-mono">trade.write</span>. You can still
        browse the catalogue.
      </Alert>
    );
  }

  function update(field: keyof typeof EMPTY, value: string): void {
    setValues((current) => ({ ...current, [field]: value }));
  }

  async function submit(event: React.FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setError(null);
    setNotice(null);
    if (!values.sku.trim() || !values.name.trim()) {
      setError("SKU and name are required.");
      return;
    }
    if (Number.parseFloat(values.unit_price) < 0 || values.unit_price === "") {
      setError("Enter a non-negative unit price.");
      return;
    }
    setPending(true);
    const result = await createProduct(
      {
        sku: values.sku.trim().toUpperCase(),
        name: values.name.trim(),
        unit: values.unit as (typeof PRODUCT_UNITS)[number],
        currency: values.currency.trim().toUpperCase(),
        unit_price: values.unit_price,
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
    setValues({ ...EMPTY });
    setOpen(false);
    setNotice(`${result.data.sku} added.`);
    router.refresh();
  }

  if (!open) {
    return (
      <div className="space-y-3">
        {notice ? <Alert variant="success">{notice}</Alert> : null}
        <Button type="button" variant="outline" size="sm" onClick={() => setOpen(true)}>
          <Plus className="size-3.5" aria-hidden />
          New product
        </Button>
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="panel space-y-4 rounded-xl p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <span className="eyebrow">New product</span>
          <p className="mt-1 text-[11.5px] text-mist-600">
            SKUs are unique per company and stored in upper case.
          </p>
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label="Close form"
          onClick={() => setOpen(false)}
        >
          <X className="size-4" aria-hidden />
        </Button>
      </div>

      {error ? <Alert variant="danger">{error}</Alert> : null}

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="product-sku">SKU</Label>
          <Input
            id="product-sku"
            value={values.sku}
            onChange={(event) => update("sku", event.target.value)}
            placeholder="ALU-A7"
            maxLength={40}
            required
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="product-name">Name</Label>
          <Input
            id="product-name"
            value={values.name}
            onChange={(event) => update("name", event.target.value)}
            placeholder="Aluminium ingot A7"
            maxLength={160}
            required
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="product-unit">Unit</Label>
          <Select
            id="product-unit"
            value={values.unit}
            onChange={(event) => update("unit", event.target.value)}
          >
            {PRODUCT_UNITS.map((unit) => (
              <option key={unit} value={unit}>
                {unit}
              </option>
            ))}
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="product-currency">Currency</Label>
          <Input
            id="product-currency"
            value={values.currency}
            onChange={(event) => update("currency", event.target.value)}
            maxLength={3}
            placeholder="USD"
            required
          />
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor="product-price">Unit price</Label>
          <Input
            id="product-price"
            value={values.unit_price}
            onChange={(event) => update("unit_price", event.target.value)}
            inputMode="decimal"
            placeholder="2450.0000"
            required
          />
        </div>
      </div>

      <div className="flex items-center gap-2">
        <Button type="submit" size="sm" disabled={pending}>
          {pending ? <Loader2 className="size-3.5 animate-spin" aria-hidden /> : null}
          {pending ? "Saving…" : "Create product"}
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={() => setOpen(false)}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
