/**
 * Exposes the current pathname to server layouts as `x-pathname`.
 *
 * Server components cannot read the pathname directly, and the authenticated
 * layout needs it to build a correct `?next=` redirect. This proxy only copies a
 * value; it performs no authentication, so a defect here cannot grant access.
 * Every layout still validates the session with the API.
 */

import { NextResponse, type NextRequest } from "next/server";

export function proxy(request: NextRequest): NextResponse {
  const headers = new Headers(request.headers);
  headers.set("x-pathname", request.nextUrl.pathname);
  return NextResponse.next({ request: { headers } });
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|api/).*)"],
};
