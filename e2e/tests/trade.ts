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
  supplierId: string;
  productId: string;
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
      supplierId: String(supplier.id),
      productId: String(product.id),
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

export interface LogisticsFixture extends ApprovedQuote {
  orderId: string;
  orderNumber: string;
  purchaseOrderId: string;
  purchaseOrderNumber: string;
  /** A second purchase order that is still a draft, so the workflow can be exercised in the browser. */
  draftPurchaseOrderId: string;
  draftPurchaseOrderNumber: string;
  shipmentId: string;
  shipmentNumber: string;
  documentTitle: string;
}

async function upload(
  api: APIRequestContext,
  fields: Record<string, string>,
  file: { name: string; mimeType: string; buffer: Buffer },
): Promise<Json> {
  const response = await api.post("/api/v1/documents", {
    multipart: { ...fields, file },
    headers: { Origin: stack().web, "Idempotency-Key": randomUUID() },
  });
  const text = await response.text();
  if (!response.ok()) {
    throw new Error(`POST /api/v1/documents -> ${response.status()}: ${text.slice(0, 300)}`);
  }
  return JSON.parse(text) as Json;
}

/**
 * A converted order with one fully procured purchase order (supplier confirmed), a second purchase
 * order still in draft, one shipment of 40 of the 100 kg that is in transit with an incurred
 * freight cost and a container reference, and a delivery-confirmation document attached to it.
 * Everything goes through the HTTP API the screens use; the browser tests then read and extend it.
 */
export async function prepareLogistics(
  browser: Browser,
  browserName: string,
): Promise<LogisticsFixture> {
  const approved = await prepareApprovedQuote(browser, browserName);
  const tag = runId();
  const sales = await signedInContext(browser, "sales", browserName);
  const finance = await signedInContext(browser, "finance", browserName);
  try {
    const api = sales.request;
    const acceptance = await call(
      api,
      "post",
      `/api/v1/deals/${approved.dealId}/customer-acceptance`,
      {
        channel: "SIGNED_QUOTE",
        accepted_at: new Date().toISOString(),
        accepted_by_name: "Dana Buyer",
        evidence_reference: `signed quote ${tag}`,
      },
    );
    const order = await call(api, "post", `/api/v1/deals/${approved.dealId}/sales-order`, {
      sales_quote_id: approved.salesQuoteId,
      acceptance_evidence_id: acceptance.id,
    });

    const poBody = {
      sales_order_id: order.id,
      supplier_id: approved.supplierId,
      supplier_quote_id: approved.supplierQuoteId,
      incoterm: "CIF",
      named_delivery_place: "Rotterdam, NL",
      payment_terms: "30 days net",
      items: [
        { product_id: approved.productId, quantity: "100.000", unit: "kg", unit_cost: "1.6000" },
      ],
    };
    let po = await call(api, "post", "/api/v1/purchase-orders", poBody);
    const transitionPo = (client: APIRequestContext, body: Json) =>
      call(client, "post", `/api/v1/purchase-orders/${po.id}/transitions`, body, {
        "If-Match": etag(po),
      });
    po = await transitionPo(finance.request, { target: "APPROVED" });
    po = await transitionPo(api, {
      target: "RECORDED_SENT",
      dispatch_channel: "EMAIL",
      dispatch_reference: `SMTP-${tag}`,
    });
    po = await transitionPo(api, {
      target: "SUPPLIER_CONFIRMED",
      supplier_confirmation_reference: `SUP-ACK-${tag}`,
      evidence_reference: "email: supplier acknowledgement",
    });
    const draftPo = await call(api, "post", "/api/v1/purchase-orders", {
      ...poBody,
      items: [
        { product_id: approved.productId, quantity: "10.000", unit: "kg", unit_cost: "1.6000" },
      ],
    });

    const items = order.items as Json[];
    let shipment = await call(api, "post", "/api/v1/shipments", {
      sales_order_id: order.id,
      transport_mode: "SEA",
      origin: "Mersin, TR",
      destination: "Rotterdam, NL",
      carrier: "Maersk",
      forwarder: "Kuehne+Nagel",
      planned_dispatch_at: new Date(Date.now() + 3 * 86_400_000).toISOString(),
      estimated_arrival_at: new Date(Date.now() + 21 * 86_400_000).toISOString(),
      items: [{ sales_order_item_id: items[0].id, quantity: "40.000" }],
    });
    const transitionShipment = async (body: Json) => {
      shipment = await call(api, "post", `/api/v1/shipments/${shipment.id}/transitions`, body, {
        "If-Match": etag(shipment),
      });
    };
    await transitionShipment({ target: "BOOKED" });
    await transitionShipment({
      target: "DISPATCHED",
      tracking_reference: `MSKU${tag}`,
      tracking_source: "MANUAL",
    });
    await transitionShipment({ target: "IN_TRANSIT" });
    await call(api, "post", `/api/v1/shipments/${shipment.id}/costs`, {
      cost_type: "FREIGHT",
      stage: "INCURRED",
      amount: "512.50",
      currency: "USD",
      reference: `INV-${tag}`,
    });
    await call(api, "post", `/api/v1/shipments/${shipment.id}/references`, {
      reference_type: "CONTAINER",
      reference_value: `MSKU${tag}`,
      provenance: "DOCUMENT_EVIDENCE",
    });

    const documentTitle = `Signed proof of delivery ${tag}`;
    await upload(
      api,
      {
        document_type: "DELIVERY_CONFIRMATION",
        linked_entity_type: "SHIPMENT",
        linked_entity_id: String(shipment.id),
        title: documentTitle,
      },
      { name: "pod.pdf", mimeType: "application/pdf", buffer: PDF },
    );

    return {
      ...approved,
      orderId: String(order.id),
      orderNumber: String(order.order_number),
      purchaseOrderId: String(po.id),
      purchaseOrderNumber: String(po.po_number),
      draftPurchaseOrderId: String(draftPo.id),
      draftPurchaseOrderNumber: String(draftPo.po_number),
      shipmentId: String(shipment.id),
      shipmentNumber: String(shipment.shipment_number),
      documentTitle,
    };
  } finally {
    await sales.close();
    await finance.close();
  }
}

/** The smallest file the document store accepts as a PDF. */
export const PDF = Buffer.from("%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n%%EOF\n");
