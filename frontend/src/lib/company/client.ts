"use client";

import { parseErrorEnvelope } from "@/lib/api/client";
import { BROWSER_API_PREFIX } from "@/lib/api/config";
import type { components } from "@/lib/api/schema";

export type CompanyProfile = components["schemas"]["CompanyProfileResponse"];
export type CompanyProfileValues = components["schemas"]["CompanyProfileRequest"];

export type SaveResult =
  | { ok: true; profile: CompanyProfile }
  | { ok: false; code: string; message: string; conflict: boolean; fields: string[] };

/** Create (version 0) or replace the profile; later saves carry If-Match with the version. */
export async function saveCompanyProfile(
  values: CompanyProfileValues,
  version: number,
  csrfToken: string,
): Promise<SaveResult> {
  const headers: Record<string, string> = {
    accept: "application/json",
    "content-type": "application/json",
    "X-CSRF-Token": csrfToken,
  };
  if (version > 0) headers["If-Match"] = `"v${version}"`;
  try {
    const response = await fetch(`${BROWSER_API_PREFIX}/company/profile`, {
      method: "PUT",
      headers,
      body: JSON.stringify(values),
      credentials: "same-origin",
      cache: "no-store",
    });
    const payload: unknown = await response.json().catch(() => null);
    if (response.ok) return { ok: true, profile: payload as CompanyProfile };
    const envelope = parseErrorEnvelope(payload);
    const details = envelope?.error.details;
    const fields = Array.isArray(details)
      ? details.flatMap((detail) => {
          const field = (detail as { field?: unknown }).field;
          return typeof field === "string" ? [field.replace(/^body\./, "")] : [];
        })
      : [];
    return {
      ok: false,
      code: envelope?.error.code ?? `HTTP_${response.status}`,
      message: envelope?.error.message ?? "The request could not be completed.",
      conflict: response.status === 409 || response.status === 428,
      fields,
    };
  } catch {
    return {
      ok: false,
      code: "UNREACHABLE",
      message: "Cannot reach the API. Confirm the service is running and try again.",
      conflict: false,
      fields: [],
    };
  }
}
