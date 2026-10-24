"use client";

import { FileDown } from "lucide-react";
import { useState } from "react";

import { useLocale } from "@/lib/i18n/locale-provider";
import type { Locale, MessageKey } from "@/lib/i18n/messages";

export type DocumentKind =
  | "rfq"
  | "sales_quotation"
  | "proforma_invoice"
  | "order_confirmation"
  | "commercial_invoice"
  | "purchase_order"
  | "packing_list"
  | "shipment_register";

export interface DocumentRequest {
  kind: DocumentKind;
  /** Id of the record the document describes; the shipment register needs none. */
  entityId?: string;
}

const TITLE: Record<DocumentKind, MessageKey> = {
  rfq: "docRfq",
  sales_quotation: "docSalesQuotation",
  proforma_invoice: "docProformaInvoice",
  order_confirmation: "docOrderConfirmation",
  commercial_invoice: "docCommercialInvoice",
  purchase_order: "docPurchaseOrder",
  packing_list: "docPackingList",
  shipment_register: "docShipmentRegister",
};

const FORMATS = [
  { format: "pdf", label: "documentFormatPdf" },
  { format: "docx", label: "documentFormatDocx" },
  { format: "xlsx", label: "documentFormatXlsx" },
  { format: "csv", label: "documentFormatCsv" },
] as const satisfies readonly { format: string; label: MessageKey }[];

export function documentUrl(
  request: DocumentRequest,
  format: (typeof FORMATS)[number]["format"],
  locale: Locale,
): string {
  const params = new URLSearchParams({ format, locale });
  if (request.entityId) params.set("entity_id", request.entityId);
  return `/api/v1/generated-documents/${request.kind}?${params.toString()}`;
}

/**
 * Download links for documents generated from a saved record. The language defaults to the
 * interface language and can be changed per download; the file comes from the API as an
 * attachment, so nothing is stored or sent.
 */
export function DocumentDownloads({ documents }: { documents: readonly DocumentRequest[] }) {
  const { locale, t } = useLocale();
  const [chosen, setChosen] = useState<Locale | null>(null);
  const language = chosen ?? locale;

  return (
    <section className="panel space-y-4 p-5" aria-label={t("documentsTitle")}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="eyebrow">{t("documentsTitle")}</p>
          <p className="mt-1 max-w-xl text-[11.5px] text-mist-500">{t("documentsHint")}</p>
        </div>
        <label className="flex items-center gap-2 text-[11.5px] text-mist-400">
          {t("documentsLanguage")}
          <select
            value={language}
            onChange={(event) => setChosen(event.target.value === "tr" ? "tr" : "en")}
            className="rounded-md border border-white/10 bg-ink-900 px-2 py-1 text-[11.5px] text-mist-100"
          >
            <option value="en">English</option>
            <option value="tr">Türkçe</option>
          </select>
        </label>
      </div>
      <ul className="divide-y divide-white/5">
        {documents.map((request) => {
          const title = t(TITLE[request.kind]);
          return (
            <li
              key={`${request.kind}:${request.entityId ?? ""}`}
              className="flex flex-wrap items-center justify-between gap-2 py-2.5"
            >
              <span className="flex items-center gap-2 text-[12.5px] text-mist-100">
                <FileDown className="size-3.5 text-mist-500" aria-hidden />
                {title}
              </span>
              <span className="flex flex-wrap gap-1.5">
                {FORMATS.map(({ format, label }) => (
                  <a
                    key={format}
                    href={documentUrl(request, format, language)}
                    download
                    aria-label={t("documentDownload", { document: title, format: t(label) })}
                    className="rounded-md border border-white/10 px-2.5 py-1 text-[11px] font-medium text-mist-200 transition-colors hover:border-accent-400/40 hover:text-accent-300 focus-visible:outline-2 focus-visible:outline-accent-400"
                  >
                    {t(label)}
                  </a>
                ))}
              </span>
            </li>
          );
        })}
      </ul>
      <p className="text-[10.5px] text-mist-500">{t("documentsDraftNote")}</p>
    </section>
  );
}
