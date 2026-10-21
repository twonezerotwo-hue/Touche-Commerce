/** DTO aliases generated from the backend OpenAPI document (single source of truth). */

import type { components } from "@/lib/api/schema";

export type AuthSession = components["schemas"]["AuthSessionResponse"];
export type CompanyAccess = components["schemas"]["CompanyAccess"];
export type CompanyList = components["schemas"]["CompanyListResponse"];
export type SessionUser = components["schemas"]["SessionUser"];
export type SessionView = components["schemas"]["SessionView"];
export type LogoutResult = components["schemas"]["LogoutResponse"];

export type SessionState =
  | { status: "authenticated"; session: AuthSession }
  | { status: "anonymous" }
  | { status: "unavailable"; message: string };
