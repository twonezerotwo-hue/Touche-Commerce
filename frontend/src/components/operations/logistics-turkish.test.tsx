import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DocumentActions } from "./document-actions";
import { DocumentUpload } from "./document-upload";
import { PurchaseOrderActions } from "./purchase-order-actions";
import { ExtraRecord } from "./shipment-extra-record";
import { ShipmentActions } from "./shipment-actions";
import { ShipmentPlanForm, type PlannableOrder } from "./shipment-plan-form";
import { LocaleProvider } from "@/lib/i18n/locale-provider";
import { translate, type MessageKey } from "@/lib/i18n/messages";
import {
  costStageText,
  costTypeText,
  documentTypeText,
  linkedEntityText,
  operationsStatusText,
  provenanceText,
  referenceTypeText,
  shipmentEventText,
  shipmentTimingText,
  transportModeText,
} from "@/lib/i18n/value-labels";
import { formatBytes } from "@/lib/operations/format";
import {
  COST_STAGES,
  DOCUMENT_TYPES,
  LINKED_ENTITY_TYPES,
  PURCHASE_ORDER_STATUSES,
  SHIPMENT_COST_TYPES,
  SHIPMENT_REFERENCE_TYPES,
  SHIPMENT_STATUSES,
  TRANSPORT_MODES,
  type TradeDocument,
  type PurchaseOrder,
  type Shipment,
} from "@/lib/operations/types";

const refreshMock = vi.fn();
const pushMock = vi.fn();
const transitionPoMock = vi.fn();
const transitionShipmentMock = vi.fn();
const planMock = vi.fn();
const uploadMock = vi.fn();
const verifyMock = vi.fn();
const archiveMock = vi.fn();
const costMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: refreshMock, push: pushMock, replace: vi.fn(), back: vi.fn() }),
}));
vi.mock("@/lib/operations/client", () => ({
  transitionPurchaseOrder: (...args: unknown[]) => transitionPoMock(...args),
  transitionShipment: (...args: unknown[]) => transitionShipmentMock(...args),
  planShipment: (...args: unknown[]) => planMock(...args),
  uploadDocument: (...args: unknown[]) => uploadMock(...args),
  verifyDocument: (...args: unknown[]) => verifyMock(...args),
  archiveDocument: (...args: unknown[]) => archiveMock(...args),
  recordShipmentCost: (...args: unknown[]) => costMock(...args),
  recordShipmentEvent: vi.fn(),
  addShipmentReference: vi.fn(),
}));

const inTurkish = (ui: React.ReactElement) =>
  render(<LocaleProvider initialLocale="tr">{ui}</LocaleProvider>);

const tr = (key: MessageKey, params?: Record<string, string | number>) =>
  translate("tr", key, params);
const en = (key: MessageKey, params?: Record<string, string | number>) =>
  translate("en", key, params);

beforeEach(() => {
  for (const mock of [
    refreshMock,
    pushMock,
    transitionPoMock,
    transitionShipmentMock,
    planMock,
    uploadMock,
    verifyMock,
    archiveMock,
    costMock,
  ]) {
    mock.mockReset();
  }
});

function purchaseOrder(overrides: Partial<PurchaseOrder> = {}): PurchaseOrder {
  return {
    id: "po1",
    po_number: "PO-2610-001",
    status: "DRAFT",
    version: 3,
    allowed_transitions: ["APPROVED", "RECORDED_SENT", "CANCELLED"],
    ...overrides,
  } as PurchaseOrder;
}

function shipment(overrides: Partial<Shipment> = {}): Shipment {
  return {
    id: "sh1",
    shipment_number: "SH-2610-001",
    status: "PLANNED",
    version: 1,
    tracking_reference: null,
    allowed_transitions: ["DISPATCHED", "CANCELLED"],
    ...overrides,
  } as Shipment;
}

describe("logistics vocabulary", () => {
  it("has a real word for every code the API can store (nothing falls back to the raw code)", () => {
    for (const locale of [en, tr]) {
      const check = (label: string, code: string) => {
        // "CMR" is both the stored code and the name people use for the consignment note.
        if (code !== "CMR") expect(label, code).not.toBe(code);
        expect(label, code).not.toMatch(/_/);
      };
      for (const code of PURCHASE_ORDER_STATUSES) check(operationsStatusText(locale, code), code);
      for (const code of SHIPMENT_STATUSES) check(operationsStatusText(locale, code), code);
      for (const code of TRANSPORT_MODES) check(transportModeText(locale, code), code);
      for (const code of DOCUMENT_TYPES) check(documentTypeText(locale, code), code);
      for (const code of SHIPMENT_COST_TYPES) check(costTypeText(locale, code), code);
      for (const code of COST_STAGES) check(costStageText(locale, code), code);
      for (const code of SHIPMENT_REFERENCE_TYPES) check(referenceTypeText(locale, code), code);
      for (const code of LINKED_ENTITY_TYPES) check(linkedEntityText(locale, code), code);
      for (const code of ["PLANNED", "BOOKED", "DISPATCHED", "IN_TRANSIT", "ARRIVED"]) {
        check(shipmentEventText(locale, code), code);
      }
      check(shipmentEventText(locale, "DELAY_RECORDED"), "DELAY_RECORDED");
    }
  });

  it("names shipment events, cost stages, reference types and provenance in Turkish", () => {
    expect(shipmentEventText(tr, "DELAY_RECORDED")).toBe("Gecikme kaydedildi");
    expect(shipmentEventText(tr, "IN_TRANSIT")).toBe("Yolda");
    expect(costStageText(tr, "INCURRED")).toBe("Gerçekleşen");
    expect(costTypeText(tr, "HANDLING")).toBe("Elleçleme");
    expect(referenceTypeText(tr, "BILL_OF_LADING")).toBe("Konşimento");
    expect(linkedEntityText(tr, "SHIPMENT")).toBe("sevkiyat");
    expect(provenanceText(tr, "MANUAL")).toBe("Elle giriş");
    expect(provenanceText(tr, null)).toBe("Takip kaynağı kaydedilmedi");
    expect(provenanceText(en, null)).toBe("No tracking provenance recorded");
  });

  it("judges lateness only from the documented ETA, in both languages", () => {
    expect(shipmentTimingText(en, true, "2026-10-01T00:00:00Z")).toBe("Past the documented ETA");
    expect(shipmentTimingText(en, false, null)).toBe("No ETA recorded");
    expect(shipmentTimingText(tr, false, "2026-11-01T00:00:00Z")).toBe(
      "Belgelenen tahmini varış içinde",
    );
    expect(shipmentTimingText(tr, false, null)).toBe("Tahmini varış kaydedilmedi");
  });

  it("formats file sizes with the reader's decimal separator", () => {
    expect(formatBytes(512, "tr")).toBe("512 B");
    expect(formatBytes(1536)).toBe("1.5 KB");
    expect(formatBytes(1536, "tr")).toBe("1,5 KB");
    expect(formatBytes(5 * 1024 * 1024, "tr")).toBe("5,0 MB");
  });
});

describe("purchase-order actions in Turkish", () => {
  it("offers Turkish controls and keeps the validation in Turkish", async () => {
    const user = userEvent.setup();
    inTurkish(
      <PurchaseOrderActions purchaseOrder={purchaseOrder()} csrfToken="c" canWrite canApprove />,
    );

    expect(
      screen.getByRole("button", { name: "Satın alma siparişini onayla" }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "İşaretle: gönderildi (kayıtlı)" }));
    expect(screen.getByText(/Bu siparişi platform dışında gönderdiğinizi kaydedin/)).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Onayla" }));
    expect(await screen.findByText(/Harici referansı kaydedin/)).toBeInTheDocument();
    expect(transitionPoMock).not.toHaveBeenCalled();
  });

  it("records the send with its channel and reference and reports it in Turkish", async () => {
    const user = userEvent.setup();
    transitionPoMock.mockResolvedValue({ ok: true, data: { status: "RECORDED_SENT" } });
    inTurkish(
      <PurchaseOrderActions purchaseOrder={purchaseOrder()} csrfToken="c" canWrite canApprove />,
    );

    await user.click(screen.getByRole("button", { name: "İşaretle: gönderildi (kayıtlı)" }));
    await user.type(screen.getByLabelText("Harici referans"), "MSG-42");
    await user.click(screen.getByRole("button", { name: "Onayla" }));

    await waitFor(() => expect(transitionPoMock).toHaveBeenCalledTimes(1));
    const [id, body, csrf, etag] = transitionPoMock.mock.calls[0] as [
      string,
      Record<string, unknown>,
      string,
      string,
    ];
    expect([id, csrf, etag]).toEqual(["po1", "c", '"v3"']);
    expect(body).toMatchObject({
      target: "RECORDED_SENT",
      dispatch_channel: "EMAIL",
      dispatch_reference: "MSG-42",
    });
    expect(
      await screen.findByText("Satın alma siparişi artık: gönderildi (kayıtlı)."),
    ).toBeInTheDocument();
  });

  it("explains in Turkish that a finished purchase order cannot move", () => {
    inTurkish(
      <PurchaseOrderActions
        purchaseOrder={purchaseOrder({ status: "CANCELLED", allowed_transitions: [] })}
        csrfToken="c"
        canWrite
        canApprove
      />,
    );
    expect(screen.getByText("Başka geçiş yok")).toBeInTheDocument();
    expect(
      screen.getByText("Bu satın alma siparişi şu durumda: iptal edildi. Artık değiştirilemez."),
    ).toBeInTheDocument();
  });
});

describe("shipment actions in Turkish", () => {
  it("requires the booking reference before dispatch, in Turkish", async () => {
    const user = userEvent.setup();
    inTurkish(<ShipmentActions shipment={shipment()} csrfToken="c" canWrite />);

    expect(screen.getByRole("button", { name: "İşaretle: sevk edildi" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Hareket notu kaydet" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "İşaretle: sevk edildi" }));
    expect(screen.getByLabelText("Taşıyıcı / rezervasyon referansı")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Onayla" }));
    expect(
      await screen.findByText("Sevk etmeden önce taşıyıcı veya rezervasyon referansını kaydedin."),
    ).toBeInTheDocument();
    expect(transitionShipmentMock).not.toHaveBeenCalled();
  });

  it("is read-only in Turkish without the trade permission", () => {
    inTurkish(<ShipmentActions shipment={shipment()} csrfToken="c" canWrite={false} />);
    expect(screen.getByText("Salt okunur erişim")).toBeInTheDocument();
    expect(
      screen.getByText("Sevkiyat aşamalarını kaydetmek için trade.write gerekir."),
    ).toBeInTheDocument();
  });
});

describe("shipment cost form in Turkish", () => {
  it("shows cost types and stages as words, and still stores the codes", async () => {
    const user = userEvent.setup();
    costMock.mockResolvedValue({ ok: true, data: {} });
    inTurkish(<ExtraRecord kind="cost" shipmentId="sh1" csrfToken="c" onDone={() => undefined} />);

    expect(screen.getByRole("option", { name: "Elleçleme" })).toHaveValue("HANDLING");
    expect(screen.getByRole("option", { name: "Gerçekleşen" })).toHaveValue("INCURRED");
    expect(screen.getByLabelText("Aşama (asla üzerine yazılmaz)")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Tutar"), "125.50");
    await user.click(screen.getByRole("button", { name: "Kaydet" }));
    await waitFor(() => expect(costMock).toHaveBeenCalledTimes(1));
    expect(costMock.mock.calls[0][1]).toMatchObject({
      cost_type: "FREIGHT",
      stage: "ESTIMATED",
      amount: "125.50",
    });
  });
});

describe("shipment planning form in Turkish", () => {
  const orders: PlannableOrder[] = [
    {
      id: "o1",
      order_number: "SO-2610-001",
      customer_name: "Buyer Ltd",
      currency: "USD",
      lines: [
        {
          id: "l1",
          sku: "STL-01",
          description: "Steel coil",
          unit: "t",
          ordered: "20",
          allocated: "0",
          delivered: "0",
          remaining: "1250.5",
        },
      ],
    },
  ];

  it("labels the fields, the transport modes and the remaining quantity in Turkish", () => {
    inTurkish(<ShipmentPlanForm orders={orders} csrfToken="c" canWrite />);
    expect(screen.getByLabelText("Taşıma modu")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Deniz" })).toHaveValue("SEA");
    expect(screen.getByRole("option", { name: "Karayolu" })).toHaveValue("ROAD");
    expect(screen.getByText("Kalan 1.250,5 t")).toBeInTheDocument();
    expect(screen.getByLabelText("STL-01 için miktar")).toHaveValue("1250.5");
  });

  it("asks for the route in Turkish before calling the API", async () => {
    const user = userEvent.setup();
    inTurkish(<ShipmentPlanForm orders={orders} csrfToken="c" canWrite />);
    await user.click(screen.getByRole("button", { name: "Sevkiyat planla" }));
    expect(await screen.findByText("Hem çıkış hem varış yerini kaydedin.")).toBeInTheDocument();
    expect(planMock).not.toHaveBeenCalled();
  });

  it("says so in Turkish when there is nothing to ship", () => {
    inTurkish(<ShipmentPlanForm orders={[]} csrfToken="c" canWrite />);
    expect(screen.getByText("Sevk edilebilir sipariş yok")).toBeInTheDocument();
  });
});

describe("document upload and actions in Turkish", () => {
  it("refuses an oversize file with Turkish sizes and does not call the API", async () => {
    const user = userEvent.setup();
    inTurkish(
      <DocumentUpload
        csrfToken="c"
        canWrite
        maxBytes={1536}
        entityType="SHIPMENT"
        entityId="sh1"
        entityLabel="sevkiyat SH-1"
      />,
    );

    expect(screen.getByText(/Eklendiği kayıt: sevkiyat SH-1\. En fazla 1,5 KB\./)).toBeVisible();
    expect(screen.getByRole("option", { name: "Konşimento" })).toHaveValue("BILL_OF_LADING");

    const big = new File([new Uint8Array(4096)], "pod.pdf", { type: "application/pdf" });
    await user.upload(screen.getByLabelText("Dosya"), big);
    await user.click(screen.getByRole("button", { name: "Belgeyi yükle" }));
    expect(await screen.findByText("Bu dosya 4,0 KB; sınır 1,5 KB.")).toBeInTheDocument();
    expect(uploadMock).not.toHaveBeenCalled();
  });

  it("is read-only in Turkish without the trade permission", () => {
    inTurkish(
      <DocumentUpload
        csrfToken="c"
        canWrite={false}
        maxBytes={1024}
        entityType="SALES_ORDER"
        entityId="o1"
        entityLabel="sipariş SO-1"
      />,
    );
    expect(screen.getByText("Salt okunur erişim")).toBeInTheDocument();
    expect(screen.getByText("Yüklemek için trade.write gerekir.")).toBeInTheDocument();
  });

  it("offers verify, reject and archive in Turkish for an active document", () => {
    inTurkish(
      <DocumentActions
        document={{ id: "d1", status: "ACTIVE" } as TradeDocument}
        csrfToken="c"
        canWrite
      />,
    );
    expect(screen.getByRole("button", { name: "Doğrula" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reddet" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Arşivle" })).toBeInTheDocument();
  });

  it("shows an archived document as archived in Turkish", () => {
    inTurkish(
      <DocumentActions
        document={{ id: "d1", status: "ARCHIVED" } as TradeDocument}
        csrfToken="c"
        canWrite
      />,
    );
    expect(screen.getByText("Arşivlendi")).toBeInTheDocument();
  });
});
