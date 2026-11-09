/**
 * Words for the financial intelligence screens.
 *
 * The English screens have always shown stored codes as upper-case words ("PURCHASE COMMITMENT");
 * that wording is kept exactly. Turkish gets real words from the catalogue, and a code the catalogue
 * does not know falls back to the same upper-case words, so a new backend code never disappears.
 */

import { humanize, type Completeness, type IntelligenceMetric } from "@/lib/finance/intelligence";
import type { Locale, MessageKey } from "@/lib/i18n/messages";
import {
  costBasisText,
  costStageText,
  costTypeText,
  discrepancyCodeText,
  financeSourceTypeText,
  fulfilmentModelText,
  operationsStatusText,
  reconciliationStatusText,
  reviewDecisionText,
  verificationText,
} from "@/lib/i18n/value-labels";

export type Translate = (key: MessageKey, params?: Record<string, string | number>) => string;
type Words = (t: (key: MessageKey) => string, code: string) => string;

/** A stored code as words: catalogue text in Turkish, the established upper-case words in English. */
export function localized(t: Translate, locale: Locale, code: string, words: Words): string {
  return locale === "tr" ? words(t, code) : humanize(code);
}

export const statusWord = (t: Translate, locale: Locale, code: string): string =>
  localized(t, locale, code, operationsStatusText);
export const modelWord = (t: Translate, locale: Locale, code: string): string =>
  localized(t, locale, code, fulfilmentModelText);
export const exceptionCodeWord = (t: Translate, locale: Locale, code: string): string =>
  localized(t, locale, code, discrepancyCodeText);
export const costTypeWord = (t: Translate, locale: Locale, code: string): string =>
  localized(t, locale, code, costTypeText);
export const basisWord = (t: Translate, locale: Locale, code: string): string =>
  localized(t, locale, code, costBasisText);
export const verificationWord = (t: Translate, locale: Locale, code: string): string =>
  localized(t, locale, code, verificationText);
export const decisionWord = (t: Translate, locale: Locale, code: string): string =>
  localized(t, locale, code, reviewDecisionText);
export const sourceTypeWord = (t: Translate, locale: Locale, code: string): string =>
  localized(t, locale, code, financeSourceTypeText);
export const stageWord = (t: Translate, locale: Locale, code: string): string =>
  locale === "tr" ? costStageText(t, code) : code;

const COMPLETENESS: Record<Completeness, MessageKey> = {
  COMPLETE: "cmpComplete",
  PARTIAL: "cmpPartial",
  MISSING: "cmpMissing",
  UNAVAILABLE: "cmpUnavailable",
};

/** COMPLETE / PARTIAL / MISSING / UNAVAILABLE; English keeps the stored word. */
export const completenessWord = (t: Translate, value: Completeness): string =>
  t(COMPLETENESS[value]);

const MISSING_INPUT: Record<string, MessageKey> = {
  CANCELLED_ORDER: "misCancelledOrder",
  PRICING_ESTIMATE: "misPricingEstimate",
  ESTIMATE_CURRENCY_MISMATCH: "misEstimateCurrencyMismatch",
  PRICING_ESTIMATE_INCOMPLETE: "misPricingEstimateIncomplete",
  ESTIMATE_FX_UNAVAILABLE: "misEstimateFxUnavailable",
  CURRENCY_MISMATCH_PURCHASE: "misCurrencyMismatchPurchase",
  PURCHASE_COMMITMENT: "misPurchaseCommitment",
  PURCHASE_COMMITMENT_INCOMPLETE: "misPurchaseCommitmentIncomplete",
  CURRENCY_MISMATCH_COST: "misCurrencyMismatchCost",
  SHIPMENT_COST_MISSING: "misShipmentCostMissing",
  DOCUMENTED_OPERATIONAL_COSTS: "misDocumentedOperationalCosts",
  PARTIAL_FULFILMENT: "misPartialFulfilment",
};

/** A missing input, or a category of a ranked chart (discrepancy code, reconciliation status ...). */
export function categoryWord(t: Translate, locale: Locale, key: string): string {
  if (locale !== "tr") return humanize(key);
  const missing = MISSING_INPUT[key];
  if (missing) return t(missing);
  const reconciliation = reconciliationStatusText(t, key);
  // reconciliationStatusText falls back to the code with spaces; use it only for a known status.
  if (reconciliation !== key.replaceAll("_", " ")) return reconciliation;
  const code = discrepancyCodeText(t, key);
  return code !== key.replaceAll("_", " ") ? code : humanize(key);
}

const METRIC_TEXT: Record<string, { label: MessageKey; meaning: MessageKey }> = {
  accepted_sales_order_value: { label: "metAcceptedLabel", meaning: "metAcceptedMeaning" },
  purchase_commitments: { label: "metCommitmentsLabel", meaning: "metCommitmentsMeaning" },
  estimated_gross_profit: { label: "metEstProfitLabel", meaning: "metEstProfitMeaning" },
  estimated_gross_margin: { label: "metEstMarginLabel", meaning: "metEstMarginMeaning" },
  recorded_operational_costs: { label: "metRecordedLabel", meaning: "metRecordedMeaning" },
  reconciliation_coverage: { label: "metCoverageLabel", meaning: "metCoverageMeaning" },
  open_discrepancies: { label: "metOpenLabel", meaning: "metOpenMeaning" },
  committed_gross_profit: {
    label: "metCommittedProfitLabel",
    meaning: "metCommittedProfitMeaning",
  },
};

/**
 * The backend writes each metric's label and meaning in English. Turkish shows the catalogue's
 * translation for the eight known metric keys; English, and any key the catalogue does not know,
 * shows the backend's own text, so a new metric still has words.
 */
export function metricTexts(
  t: Translate,
  locale: Locale,
  metric: Pick<IntelligenceMetric, "key" | "label" | "meaning">,
): { label: string; meaning: string } {
  const known = locale === "tr" ? METRIC_TEXT[metric.key] : undefined;
  if (!known) return { label: metric.label, meaning: metric.meaning };
  if (metric.key === "open_discrepancies") {
    const blocking = /(\d+)\s+blocking/.exec(metric.meaning)?.[1];
    return {
      label: t(known.label),
      meaning: blocking === undefined ? metric.meaning : t(known.meaning, { blocking }),
    };
  }
  return { label: t(known.label), meaning: t(known.meaning) };
}
