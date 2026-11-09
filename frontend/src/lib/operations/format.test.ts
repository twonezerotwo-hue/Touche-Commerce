import { describe, expect, it } from "vitest";

import {
  completionPercent,
  costStageLabel,
  delayLabel,
  documentTypeLabel,
  evidenceProvenanceLabel,
  formatBytes,
  operationsStatusLabel,
  operationsStatusTone,
  transportModeLabel,
  unallocatedQuantity,
} from "./format";

describe("operations presentation helpers", () => {
  it("labels execution statuses without leaking the raw enum", () => {
    expect(operationsStatusLabel("IN_FULFILLMENT")).toBe("In fulfillment");
    expect(operationsStatusLabel("RECORDED_SENT")).toBe("Sent (recorded)");
    expect(operationsStatusTone("DELIVERED")).toBe("success");
    expect(operationsStatusTone("CANCELLED")).toBe("outline");
  });

  it("falls back neutrally for an unknown status instead of inventing a tone", () => {
    expect(operationsStatusLabel("SOMETHING_NEW")).toBe("SOMETHING_NEW");
    expect(operationsStatusTone("SOMETHING_NEW")).toBe("secondary");
  });

  it("names trade document types and transport modes", () => {
    expect(documentTypeLabel("BILL_OF_LADING")).toBe("Bill of lading");
    expect(documentTypeLabel("CMR_CONSIGNMENT_NOTE")).toBe("CMR consignment note");
    expect(transportModeLabel("MULTIMODAL")).toBe("Multimodal");
    expect(transportModeLabel("SEA")).toBe("Sea");
    expect(costStageLabel("INCURRED")).toBe("Incurred");
  });

  it("formats byte sizes without false precision", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(2048)).toBe("2.0 KB");
    expect(formatBytes(5 * 1024 * 1024)).toBe("5.0 MB");
  });

  it("renders a decimal completion ratio as a whole percentage", () => {
    expect(completionPercent("0.4000")).toBe("40%");
    expect(completionPercent("1")).toBe("100%");
    expect(completionPercent("not-a-number")).toBe("—");
  });

  it("describes delay only from the documented ETA", () => {
    expect(delayLabel(true, "2026-10-01T00:00:00Z")).toMatch(/documented ETA/i);
    expect(delayLabel(false, null)).toMatch(/no ETA/i);
    expect(delayLabel(false, "2026-11-01T00:00:00Z")).toMatch(/within/i);
  });

  it("distinguishes manual and documentary tracking provenance", () => {
    expect(evidenceProvenanceLabel("MANUAL")).toBe("Manual entry");
    expect(evidenceProvenanceLabel("DOCUMENT_EVIDENCE")).toBe("Document evidence");
    expect(evidenceProvenanceLabel(null)).toMatch(/no tracking provenance/i);
  });
});

describe("unallocatedQuantity", () => {
  it("offers what live shipments have not yet taken, not what is still undelivered", () => {
    expect(unallocatedQuantity("100.000", "40.000")).toBe("60.000");
    expect(unallocatedQuantity("100", "0")).toBe("100.000");
    expect(unallocatedQuantity("1500.5", "250")).toBe("1250.500");
  });

  it("never goes below zero and does not drift on decimal quantities", () => {
    expect(unallocatedQuantity("10.000", "10.000")).toBe("0.000");
    expect(unallocatedQuantity("10.000", "12.000")).toBe("0.000");
    expect(unallocatedQuantity("0.300", "0.100")).toBe("0.200");
    expect(unallocatedQuantity("not-a-number", "0")).toBe("0.000");
  });
});
