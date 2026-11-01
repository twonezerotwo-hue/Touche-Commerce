import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DocumentActions } from "./document-actions";
import { DocumentUpload } from "./document-upload";
import { PurchaseOrderActions } from "./purchase-order-actions";
import { ShipmentActions } from "./shipment-actions";
import { ShipmentPlanForm, type PlannableOrder } from "./shipment-plan-form";
import { LocaleProvider } from "@/lib/i18n/locale-provider";
import { translate } from "@/lib/i18n/messages";
import {
  costStageText,
  delayText,
  entityTypeText,
  provenanceText,
  referenceTypeText,
  shipmentCostTypeText,
  shipmentEventText,
} from "@/lib/i18n/value-labels";
import type { PurchaseOrder, Shipment, TradeDocument } from "@/lib/operations/types";

const refreshMock = vi.fn();
const poMock = vi.fn();
const shipmentMock = vi.fn();
const planMock = vi.fn();
const uploadMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: refreshMock, push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));
vi.mock("@/lib/operations/client", () => ({
  transitionPurchaseOrder: (...args: unknown[]) => poMock(...args),
  transitionShipment: (...args: unknown[]) => shipmentMock(...args),
  planShipment: (...args: unknown[]) => planMock(...args),
  uploadDocument: (...args: unknown[]) => uploadMock(...args),
  archiveDocument: vi.fn(),
  verifyDocument: vi.fn(),
  recordShipmentEvent: vi.fn(),
  recordShipmentCost: vi.fn(),
  addShipmentReference: vi.fn(),
}));

const inTurkish = (ui: React.ReactElement) =>
  render(<LocaleProvider initialLocale="tr">{ui}</LocaleProvider>);
const tr = (key: Parameters<typeof translate>[1]) => translate("tr", key);

const purchaseOrder = (overrides: Partial<PurchaseOrder> = {}): PurchaseOrder =>
  ({
    id: "po-1",
    status: "APPROVED",
    version: 3,
    allowed_transitions: ["RECORDED_SENT", "CANCELLED"],
    ...overrides,
  }) as PurchaseOrder;

const shipment = (overrides: Partial<Shipment> = {}): Shipment =>
  ({
    id: "sh-1",
    status: "BOOKED",
    version: 2,
    tracking_reference: null,
    allowed_transitions: ["DISPATCHED", "DELIVERED", "CANCELLED"],
    ...overrides,
  }) as Shipment;

const orders: PlannableOrder[] = [
  {
    id: "o1",
    order_number: "SO-2610-001",
    customer_name: "Buyer Ltd",
    currency: "USD",
    lines: [
      {
        id: "l1",
        sku: "ALM-01",
        description: "",
        unit: "kg",
        ordered: "1000.000",
        allocated: "0.000",
        delivered: "0.000",
        remaining: "1000.000",
      },
    ],
  },
];

beforeEach(() => {
  for (const mock of [refreshMock, poMock, shipmentMock, planMock, uploadMock]) mock.mockReset();
});

describe("logistics words", () => {
  it("translates milestones, cost types, stages, references and record kinds", () => {
    expect(shipmentEventText(tr, "IN_TRANSIT")).toBe("Yolda");
    expect(shipmentEventText(tr, "DELAY_RECORDED")).toBe("Gecikme kaydedildi");
    expect(shipmentCostTypeText(tr, "CUSTOMS_BROKERAGE")).toBe("Gümrük müşavirliği");
    expect(costStageText(tr, "INCURRED")).toBe("Gerçekleşen");
    expect(costStageText(tr, "ESTIMATED")).toBe("Tahmini");
    expect(referenceTypeText(tr, "BILL_OF_LADING")).toBe("Konşimento");
    expect(entityTypeText(tr, "PURCHASE_ORDER")).toBe("Satın alma siparişi");
    expect(shipmentEventText(tr, "NEW_EVENT")).toBe("NEW EVENT");
  });

  it("never turns an ETA into an arrival and says so for each case", () => {
    expect(delayText(tr, true, "2026-10-01T00:00:00Z")).toBe(
      "Belgelenen tahmini varış tarihi geçti",
    );
    expect(delayText(tr, false, null)).toBe("Tahmini varış kaydı yok");
    expect(delayText(tr, false, "2026-12-01T00:00:00Z")).toBe(
      "Belgelenen tahmini varış tarihi içinde",
    );
    expect(provenanceText(tr, null)).toBe("Takip kaynağı kaydedilmedi");
    expect(provenanceText(tr, "MANUAL")).toBe("Elle giriş");
  });
});

describe("purchase order panel in Turkish", () => {
  it("asks for the external reference before a send can be recorded", async () => {
    const user = userEvent.setup();
    inTurkish(
      <PurchaseOrderActions
        purchaseOrder={purchaseOrder()}
        csrfToken="c"
        canWrite
        canApprove={false}
      />,
    );
    await user.click(
      screen.getByRole("button", { name: "Şu olarak işaretle: gönderildi (kayıtlı)" }),
    );
    expect(
      screen.getByText(
        "Bu siparişi platform dışında gönderdiğinizi kaydedin. TOUCHE hiçbir şey iletmez.",
      ),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Onayla" }));
    expect(
      await screen.findByText(
        "Dış referansı kaydedin (ileti numarası, WhatsApp dökümü, portal makbuzu).",
      ),
    ).toBeInTheDocument();
    expect(poMock).not.toHaveBeenCalled();
  });

  it("hides approval from someone without finance.approve", () => {
    inTurkish(
      <PurchaseOrderActions
        purchaseOrder={purchaseOrder({ status: "DRAFT", allowed_transitions: ["APPROVED"] })}
        csrfToken="c"
        canWrite
        canApprove={false}
      />,
    );
    expect(screen.getByText("Başka geçiş yok")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Satın alma siparişini onayla" })).toBeNull();
  });
});

describe("shipment milestones in Turkish keep their evidence rules", () => {
  it("will not dispatch without a booking reference", async () => {
    const user = userEvent.setup();
    inTurkish(<ShipmentActions shipment={shipment()} csrfToken="c" canWrite />);
    await user.click(screen.getByRole("button", { name: "Şu olarak işaretle: sevk edildi" }));
    await user.click(screen.getByRole("button", { name: "Onayla" }));
    expect(
      await screen.findByText("Sevk etmeden önce taşıyıcı veya rezervasyon referansını kaydedin."),
    ).toBeInTheDocument();
    expect(shipmentMock).not.toHaveBeenCalled();
  });

  it("will not mark a shipment delivered without proof of delivery", async () => {
    const user = userEvent.setup();
    inTurkish(<ShipmentActions shipment={shipment()} csrfToken="c" canWrite />);
    await user.click(screen.getByRole("button", { name: "Şu olarak işaretle: teslim edildi" }));
    await user.click(screen.getByRole("button", { name: "Onayla" }));
    expect(
      await screen.findByText("Teslimat için imzalı bir teslim belgesi referansı gerekir."),
    ).toBeInTheDocument();
    expect(shipmentMock).not.toHaveBeenCalled();
  });

  it("needs a reason to cancel and is read-only without trade.write", async () => {
    const user = userEvent.setup();
    const { unmount } = inTurkish(<ShipmentActions shipment={shipment()} csrfToken="c" canWrite />);
    await user.click(screen.getByRole("button", { name: "Şu olarak işaretle: iptal edildi" }));
    await user.click(screen.getByRole("button", { name: "Onayla" }));
    expect(
      await screen.findByText("Bir sevkiyatı iptal etmek için gerekçe gerekir."),
    ).toBeInTheDocument();
    unmount();

    inTurkish(<ShipmentActions shipment={shipment()} csrfToken="c" canWrite={false} />);
    expect(screen.getByText("Salt okunur erişim")).toBeInTheDocument();
    expect(
      screen.getByText("Sevkiyat aşamalarını kaydetmek için trade.write gerekir."),
    ).toBeInTheDocument();
  });
});

describe("shipment planning form in Turkish", () => {
  it("labels the form, translates the transport modes and validates before calling the API", async () => {
    const user = userEvent.setup();
    inTurkish(<ShipmentPlanForm orders={orders} csrfToken="c" canWrite />);
    expect(screen.getByLabelText("Taşıma türü")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Deniz" })).toHaveValue("SEA");
    expect(screen.getByText("Kalan 1000.000 kg")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Sevkiyat planla" }));
    expect(await screen.findByText("Hem çıkış hem varış yerini kaydedin.")).toBeInTheDocument();
    expect(planMock).not.toHaveBeenCalled();
  });

  it("explains a missing permission and an empty order list", () => {
    const { unmount } = inTurkish(
      <ShipmentPlanForm orders={orders} csrfToken="c" canWrite={false} />,
    );
    expect(screen.getByText("Sevkiyat planlamak için trade.write gerekir.")).toBeInTheDocument();
    unmount();
    inTurkish(<ShipmentPlanForm orders={[]} csrfToken="c" canWrite />);
    expect(screen.getByText("Sevk edilebilir sipariş yok")).toBeInTheDocument();
  });
});

describe("document upload and actions in Turkish", () => {
  it("asks for a file, lists the document types as words and keeps their codes", async () => {
    const user = userEvent.setup();
    inTurkish(
      <DocumentUpload
        csrfToken="c"
        canWrite
        maxBytes={1024}
        entityType="SHIPMENT"
        entityId="sh-1"
        entityLabel="sevkiyat SH-1"
      />,
    );
    expect(screen.getByRole("option", { name: "Konşimento" })).toHaveValue("BILL_OF_LADING");
    expect(screen.getByText(/sevkiyat SH-1 kaydına eklenir/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Belgeyi yükle" }));
    expect(await screen.findByText("Yüklemek için bir dosya seçin.")).toBeInTheDocument();
    expect(uploadMock).not.toHaveBeenCalled();
  });

  it("is read-only without trade.write", () => {
    inTurkish(
      <DocumentUpload
        csrfToken="c"
        canWrite={false}
        maxBytes={1024}
        entityType="SHIPMENT"
        entityId="sh-1"
        entityLabel="x"
      />,
    );
    expect(screen.getByText("Belge yüklemek için trade.write gerekir.")).toBeInTheDocument();
  });

  it("offers verify, reject and archive for an active document", () => {
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
});
