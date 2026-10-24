import type { Locale } from "./messages";

/**
 * Transitional shell labels for existing route metadata.
 * Presentation-only: route names and authorization keys remain unchanged.
 */
const turkishNavigation: Record<string, string> = {
  "Trade core": "Ticaret yönetimi",
  Sourcing: "Tedarik",
  Execution: "Operasyon",
  Account: "Hesap",
  Workspace: "Çalışma alanı",
  "Command Center": "Yönetim paneli",
  Deals: "Ticari fırsatlar",
  "New deal": "Yeni fırsat",
  "Deal detail": "Fırsat ayrıntısı",
  CRM: "Müşteri ve tedarikçiler",
  Products: "Ürünler",
  Import: "İçe aktar",
  "Company profile": "Şirket bilgileri",
  RFQs: "Teklif talepleri",
  "New RFQ": "Yeni teklif talebi",
  "RFQ detail": "Teklif talebi ayrıntısı",
  "Supplier quotes": "Tedarikçi teklifleri",
  "Supplier quote detail": "Tedarikçi teklif ayrıntısı",
  Pricing: "Fiyatlandırma",
  "Pricing scenario": "Fiyatlandırma senaryosu",
  "Sales quotes": "Satış teklifleri",
  "Sales quote detail": "Satış teklifi ayrıntısı",
  "FX snapshots": "Döviz kuru kayıtları",
  "Sales orders": "Satış siparişleri",
  "Sales order": "Satış siparişi",
  "Purchase orders": "Satın alma siparişleri",
  "Purchase order": "Satın alma siparişi",
  Shipments: "Sevkiyatlar",
  Shipment: "Sevkiyat",
  Logistics: "Lojistik",
  "Plan shipment": "Sevkiyat planla",
  Documents: "Belgeler",
  "Trade documents": "Dış ticaret belgeleri",
  Finance: "Finans",
  Reconciliation: "Mutabakat",
  "Reconciliation run": "Mutabakat kaydı",
  Discrepancies: "Uyuşmazlıklar",
  Intelligence: "Finansal analiz",
  "Order intelligence": "Sipariş analizi",
  "Order profitability": "Sipariş kârlılığı",
  "Order finance": "Sipariş finansı",
  "Financial exceptions": "Finansal istisnalar",
  "AI Office": "Yapay zekâ ofisi",
  Communications: "İletişim",
  "Profile & access": "Profil ve erişim",
  "Select company": "Şirket seç",
  Settings: "Ayarlar",
  "System status": "Sistem durumu",
};

/** Unknown identifiers are left untouched, never used as auth keys. */
export function localizeNavigation(locale: Locale, value: string): string {
  return locale === "tr" ? (turkishNavigation[value] ?? value) : value;
}
