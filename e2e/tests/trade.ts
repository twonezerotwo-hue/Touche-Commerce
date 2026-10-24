import { randomUUID } from "node:crypto";

import type { APIRequestContext, Browser } from "@playwright/test";

import { runId, signedInContext, stack } from "./support";

/**
 * Builds real trade records through the same HTTP API the screens use (no database shortcuts):
 * a customer, a supplier, a product, an open deal, an RFQ sent to the supplier, a supplier quote,
 * a verified pricing scenario and a sales quote that a *second* person (finance) approves. The
 * final step - customer acceptance and conversion into an order - is left to the browser test.
 */

const future = (): string => new Date(Date.now() + 30 * 86_400_000).toISOString().slice(0, 10);

type Json = Record<string, unknown>;

async function call(
  api: APIRequestContext,
  method: "post" | "get",
  path: string,
  body?: Json,
  headers: Record<string, string> = {},
): Promise<Json> {
  const response = await api[method](path, {
    data: body,
    headers: {
      Origin: stack().web,
      "Idempotency-Key": randomUUID(),
      ...headers,
    },
  });
  const text = await response.text();
  if (!response.ok()) {
    throw new Error(
      `${method.toUpperCase()} ${path} -> ${response.status()}: ${text.slice(0, 300)}`,
    );
  }
  return JSON.parse(text) as Json;
}

const etag = (record: Json): string => `"v${String(record.version)}"`;

export interface ApprovedQuote {
  dealId: string;
  dealReference: string;
  quoteNumber: string;
  customerName: string;
  supplierName: string;
  rfqId: string;
  rfqReference: string;
  supplierQuoteId: string;
  scenarioId: string;
  salesQuoteId: string;
}

export async function prepareApprovedQuote(
  browser: Browser,
  browserName: string,
): Promise<ApprovedQuote> {
  const tag = runId();
  const sales = await signedInContext(browser, "sales", browserName);
  const finance = await signedInContext(browser, "finance", browserName);
  try {
    const api = sales.request;
    const customerName = `Rotterdam Foods ${tag}`;
    const buyer = await call(api, "post", "/api/v1/counterparties", {
      name: customerName,
      type: "buyer",
      country: "NL",
    });
    const supplier = await call(api, "post", "/api/v1/counterparties", {
      name: `Anadolu Gıda ${tag}`,
      type: "supplier",
      country: "TR",
    });
    const product = await call(api, "post", "/api/v1/products", {
      sku: `E2E-${tag}`,
      name: `Almond kernels ${tag}`,
      unit: "kg",
      currency: "USD",
      unit_price: "2.0000",
    });
    let deal = await call(api, "post", "/api/v1/deals", {
      title: `Almond shipment ${tag}`,
      counterparty_id: buyer.id,
      currency: "USD",
      items: [{ product_id: product.id, quantity: "100.000", unit_price: "2.0000" }],
    });
    deal = await call(
      api,
      "post",
      `/api/v1/deals/${deal.id}/transitions`,
      { to: "OPEN" },
      {
        "If-Match": etag(deal),
      },
    );

    const rfqs = await call(api, "post", "/api/v1/rfqs", {
      deal_id: deal.id,
      supplier_ids: [supplier.id],
      requested_currency: "USD",
      delivery_location: "Rotterdam, NL",
      response_due_date: future(),
      items: [
        {
          product_id: product.id,
          description: "Almond kernels, 25 kg bags",
          quantity: "100.000",
          unit: "kg",
        },
      ],
    });
    const rfq = (rfqs.items as Json[])[0];
    await call(api, "post", `/api/v1/rfqs/${rfq.id}/transitions`, { to: "PREPARED" });
    await call(api, "post", `/api/v1/rfqs/${rfq.id}/transitions`, {
      to: "SENT",
      channel: "email",
      evidence: `message-id:<rfq-${tag}@touche.example>`,
    });
    const quote = await call(api, "post", `/api/v1/rfqs/${rfq.id}/quotes`, {
      currency: "USD",
      incoterm: "CIF",
      named_delivery_place: "Rotterdam, NL",
      payment_terms: "30 days net",
      lead_time_days: 21,
      valid_until: future(),
      source_reference: "email: supplier quote",
      items: [{ product_id: product.id, quantity: "100.000", unit_price: "1.6000" }],
    });
    const scenario = await call(api, "post", "/api/v1/pricing-scenarios", {
      supplier_quote_id: quote.id,
      target_currency: "USD",
      margin_pct: "20",
      markup_pct: "0",
      fx_rate_snapshot_id: null,
      components: [
        {
          cost_type: "FREIGHT",
          amount: "40.00",
          currency: "USD",
          basis: "ORDER",
          source_reference: "freight-invoice",
          verification_status: "VERIFIED",
          product_id: null,
        },
      ],
    });
    let salesQuote = await call(api, "post", "/api/v1/sales-quotes", {
      scenario_id: scenario.id,
      customer_id: buyer.id,
      valid_until: future(),
      incoterm: "CIF",
      named_delivery_place: "Rotterdam, NL",
      payment_terms: "30 days net",
    });
    salesQuote = await call(
      api,
      "post",
      `/api/v1/sales-quotes/${salesQuote.id}/submit`,
      undefined,
      {
        "If-Match": etag(salesQuote),
      },
    );
    salesQuote = await call(
      finance.request,
      "post",
      `/api/v1/sales-quotes/${salesQuote.id}/approve`,
      undefined,
      { "If-Match": etag(salesQuote) },
    );
    return {
      dealId: String(deal.id),
      dealReference: String(deal.reference),
      quoteNumber: String(salesQuote.quote_number),
      customerName,
      supplierName: String(supplier.name),
      rfqId: String(rfq.id),
      rfqReference: String(rfq.reference_number),
      supplierQuoteId: String(quote.id),
      scenarioId: String(scenario.id),
      salesQuoteId: String(salesQuote.id),
    };
  } finally {
    await sales.close();
    await finance.close();
  }
}

export interface MasterData {
  customerName: string;
  sku: string;
  productName: string;
}

/** A fresh customer and product, so the deal form has something unique to pick. */
export async function createMasterData(browser: Browser, browserName: string): Promise<MasterData> {
  const tag = runId();
  const sales = await signedInContext(browser, "sales", browserName);
  try {
    const customerName = `Deal Customer ${tag}`;
    await call(sales.request, "post", "/api/v1/counterparties", {
      name: customerName,
      type: "buyer",
      country: "NL",
    });
    const sku = `DEAL-${tag}`;
    const productName = `Deal product ${tag}`;
    await call(sales.request, "post", "/api/v1/products", {
      sku,
      name: productName,
      unit: "kg",
      currency: "USD",
      unit_price: "2.0000",
    });
    return { customerName, sku, productName };
  } finally {
    await sales.close();
  }
}
