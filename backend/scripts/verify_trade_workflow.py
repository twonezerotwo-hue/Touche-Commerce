"""Stage 1B end-to-end trade workflow against a running local API.

This is the executable evidence for the milestone: it drives the real API with a
real session cookie, CSRF token, idempotency keys and If-Match versions, then
checks the frontend server-side render. It uses only the standard library so it
can run without touching the backend virtualenv's dependency set.

Passwords come from the environment (never argv):
``TOUCHE_VERIFY_TRADER_PASSWORD`` and ``TOUCHE_VERIFY_ADMIN_PASSWORD``.

Exit code 0 means every check passed; 1 means at least one check failed; 2 means
the environment was not prepared (missing password, API unreachable).
"""

from __future__ import annotations

import http.cookiejar
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

BASE_URL = os.environ.get("TOUCHE_VERIFY_API", "http://127.0.0.1:8000")
FRONTEND_URL = os.environ.get("TOUCHE_VERIFY_WEB", "http://127.0.0.1:3000")
ORIGIN = os.environ.get("TOUCHE_VERIFY_ORIGIN", "http://localhost:3000")
TRADER_EMAIL = os.environ.get("TOUCHE_VERIFY_TRADER_EMAIL", "stage1b.trader@touche.example")
ADMIN_EMAIL = os.environ.get("TOUCHE_VERIFY_ADMIN_EMAIL", "stage1b.admin@touche.example")


@dataclass
class Response:
    status: int
    body: Any
    headers: dict[str, str]

    @property
    def code(self) -> str:
        if isinstance(self.body, dict):
            error = self.body.get("error")
            if isinstance(error, dict):
                return str(error.get("code", ""))
        return ""


@dataclass
class Client:
    opener: urllib.request.OpenerDirector
    csrf: str | None = None
    company: dict[str, Any] | None = None

    def call(
        self,
        method: str,
        path: str,
        body: Any | None = None,
        *,
        idempotency_key: str | None = None,
        if_match: str | None = None,
        anonymous: bool = False,
    ) -> Response:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(  # noqa: S310 - fixed http(s) base URL
            f"{BASE_URL}{path}", data=data, method=method
        )
        request.add_header("Accept", "application/json")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        if not anonymous or ORIGIN:
            request.add_header("Origin", ORIGIN)
        if self.csrf and not anonymous:
            request.add_header("X-CSRF-Token", self.csrf)
        if idempotency_key:
            request.add_header("Idempotency-Key", idempotency_key)
        if if_match:
            request.add_header("If-Match", if_match)
        try:
            with self.opener.open(request, timeout=20) as response:
                return Response(
                    status=response.status,
                    body=_decode(response.read()),
                    headers={key.lower(): value for key, value in response.headers.items()},
                )
        except urllib.error.HTTPError as error:
            return Response(
                status=error.code,
                body=_decode(error.read()),
                headers={key.lower(): value for key, value in error.headers.items()},
            )


def _decode(payload: bytes) -> Any:
    if not payload:
        return None
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return payload.decode("utf-8", errors="replace")


def new_client() -> Client:
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    return Client(opener=opener)


def connect(email: str, password: str) -> Client:
    client = new_client()
    login = client.call(
        "POST", "/api/v1/auth/login", {"email": email, "password": password}, anonymous=True
    )
    if login.status != 200:
        raise RuntimeError(f"login failed for {email}: HTTP {login.status} {login.body}")
    client.csrf = str(login.body["session"]["csrf_token"])
    client.company = login.body["session"]["company"]
    return client


def key() -> str:
    return str(uuid.uuid4())


class Checks:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0

    def check(self, name: str, condition: bool, detail: str = "") -> None:
        if condition:
            self.passed += 1
            print(f"  [pass] {name}")
        else:
            self.failed += 1
            print(f"  [FAIL] {name} {detail}".rstrip())

    def step(self, title: str) -> None:
        print(f"\n==> {title}")


def require_env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value.strip():
        raise RuntimeError(f"{name} is not set")
    return value


def run() -> int:
    checks = Checks()
    trader_password = require_env("TOUCHE_VERIFY_TRADER_PASSWORD")
    admin_password = require_env("TOUCHE_VERIFY_ADMIN_PASSWORD")

    # 1 -------------------------------------------------------------------
    checks.step("1. Trader sign-in and active company")
    trader = connect(TRADER_EMAIL, trader_password)
    company = trader.company or {}
    checks.check("trader session is authenticated", trader.csrf is not None)
    checks.check("active company is selected (single membership)", bool(company), str(company))
    checks.check("membership role is trader", company.get("role") == "trader")
    checks.check(
        "trader holds trade.write", "trade.write" in (company.get("permissions") or [])
    )

    stamp = datetime.now(tz=UTC).strftime("%H%M%S")
    counterparty_name = f"Stage1B Counterparty {stamp}"
    product_sku = f"S1B-{stamp}"

    # 2 -------------------------------------------------------------------
    checks.step("2. Create a counterparty")
    counterparty = trader.call(
        "POST",
        "/api/v1/counterparties",
        {"name": counterparty_name, "type": "buyer", "country": "GB", "contact_name": "Verify Bot"},
        idempotency_key=key(),
    )
    checks.check("counterparty created", counterparty.status == 201, f"HTTP {counterparty.status}")
    checks.check(
        "ETag v1 returned",
        counterparty.headers.get("etag") == '"v1"',
        counterparty.headers.get("etag", ""),
    )

    # 3 -------------------------------------------------------------------
    checks.step("3. Create a product")
    product = trader.call(
        "POST",
        "/api/v1/products",
        {
            "sku": product_sku,
            "name": "Verification ingot",
            "unit": "mt",
            "currency": "USD",
            "unit_price": "2450.0000",
        },
        idempotency_key=key(),
    )
    checks.check("product created", product.status == 201, f"HTTP {product.status}")

    # 4 -------------------------------------------------------------------
    checks.step("4. Create a deal with one line")
    deal_response = trader.call(
        "POST",
        "/api/v1/deals",
        {
            "title": "Stage 1B verification deal",
            "counterparty_id": counterparty.body["id"],
            "currency": "USD",
            "notes": "Created by backend/scripts/verify_trade_workflow.py",
            "items": [
                {
                    "product_id": product.body["id"],
                    "quantity": "25.000",
                    "unit_price": "2450.0000",
                }
            ],
        },
        idempotency_key=key(),
    )
    deal = deal_response.body
    checks.check(
        "deal created as DRAFT",
        deal_response.status == 201 and deal["status"] == "DRAFT",
        f"HTTP {deal_response.status}",
    )
    checks.check(
        "total value is 61250.00",
        str(deal["total_value"]) == "61250.00",
        str(deal.get("total_value")),
    )
    checks.check(
        "initial history entry is DRAFT",
        len(deal["transitions"]) == 1 and deal["transitions"][0]["to_status"] == "DRAFT",
    )
    checks.check(
        "allowed transitions are OPEN and CANCELLED",
        deal["allowed_transitions"] == ["OPEN", "CANCELLED"],
        str(deal["allowed_transitions"]),
    )
    deal_id = str(deal["id"])
    reference = str(deal["reference"])

    # 5 -------------------------------------------------------------------
    checks.step("5. List and read the deal back")
    listing = trader.call("GET", f"/api/v1/deals?search={reference}")
    checks.check(
        "list finds the new deal",
        listing.status == 200 and len(listing.body.get("items", [])) == 1,
        f"HTTP {listing.status}",
    )
    detail = trader.call("GET", f"/api/v1/deals/{deal_id}")
    checks.check(
        "detail returns ETag v1",
        detail.status == 200 and detail.headers.get("etag") == '"v1"',
        detail.headers.get("etag", ""),
    )

    # 6 -------------------------------------------------------------------
    checks.step("6. PATCH requires If-Match and rejects a stale version")
    missing = trader.call(
        "PATCH",
        f"/api/v1/deals/{deal_id}",
        {"title": "Renamed deal"},
        idempotency_key=key(),
    )
    checks.check(
        "missing If-Match returns 428 PRECONDITION_REQUIRED",
        missing.status == 428 and missing.code == "PRECONDITION_REQUIRED",
        f"HTTP {missing.status} {missing.code}",
    )
    patched = trader.call(
        "PATCH",
        f"/api/v1/deals/{deal_id}",
        {"title": "Stage 1B verification deal (renamed)"},
        idempotency_key=key(),
        if_match='"v1"',
    )
    checks.check(
        "valid If-Match updates and bumps to v2",
        patched.status == 200 and patched.body["version"] == 2,
        f"HTTP {patched.status}",
    )
    stale = trader.call(
        "PATCH",
        f"/api/v1/deals/{deal_id}",
        {"title": "Stale write"},
        idempotency_key=key(),
        if_match='"v1"',
    )
    checks.check(
        "stale If-Match returns VERSION_CONFLICT",
        stale.status == 409 and stale.code == "VERSION_CONFLICT",
        f"HTTP {stale.status} {stale.code}",
    )

    # 7 -------------------------------------------------------------------
    checks.step("7. Status cannot be changed through PATCH")
    bypass = trader.call(
        "PATCH",
        f"/api/v1/deals/{deal_id}",
        {"status": "WON"},
        idempotency_key=key(),
        if_match='"v2"',
    )
    checks.check(
        "PATCH with status is rejected with 422 VALIDATION_ERROR",
        bypass.status == 422 and bypass.code == "VALIDATION_ERROR",
        f"HTTP {bypass.status} {bypass.code}",
    )
    checks.check(
        "deal is still DRAFT",
        trader.call("GET", f"/api/v1/deals/{deal_id}").body["status"] == "DRAFT",
    )
    return _continue(checks, trader, admin_password, deal_id, reference, company)



def _continue(
    checks: Checks,
    trader: Client,
    admin_password: str,
    deal_id: str,
    reference: str,
    company: dict[str, Any],
) -> int:
    # 8 -------------------------------------------------------------------
    checks.step("8. A transition requires an Idempotency-Key")
    no_key = trader.call("POST", f"/api/v1/deals/{deal_id}/transitions", {"to": "OPEN"})
    checks.check(
        "missing key returns IDEMPOTENCY_KEY_REQUIRED",
        no_key.status == 400 and no_key.code == "IDEMPOTENCY_KEY_REQUIRED",
        f"HTTP {no_key.status} {no_key.code}",
    )

    # 9 -------------------------------------------------------------------
    checks.step("9. DRAFT -> OPEN")
    opened = trader.call(
        "POST", f"/api/v1/deals/{deal_id}/transitions", {"to": "OPEN"}, idempotency_key=key()
    )
    checks.check(
        "deal is OPEN with two history rows",
        opened.status == 200
        and opened.body["status"] == "OPEN"
        and len(opened.body["transitions"]) == 2,
        f"HTTP {opened.status}",
    )

    # 10 ------------------------------------------------------------------
    checks.step("10. OPEN -> NEGOTIATION")
    negotiation = trader.call(
        "POST",
        f"/api/v1/deals/{deal_id}/transitions",
        {"to": "NEGOTIATION"},
        idempotency_key=key(),
    )
    checks.check(
        "deal is NEGOTIATION",
        negotiation.status == 200 and negotiation.body["status"] == "NEGOTIATION",
        f"HTTP {negotiation.status}",
    )

    # 11 ------------------------------------------------------------------
    checks.step("11. WON is disabled")
    won = trader.call(
        "POST", f"/api/v1/deals/{deal_id}/transitions", {"to": "WON"}, idempotency_key=key()
    )
    checks.check(
        "WON returns TRANSITION_DISABLED",
        won.status == 409 and won.code == "TRANSITION_DISABLED",
        f"HTTP {won.status} {won.code}",
    )
    checks.check(
        "deal did not move",
        trader.call("GET", f"/api/v1/deals/{deal_id}").body["status"] == "NEGOTIATION",
    )

    # 12 ------------------------------------------------------------------
    checks.step("12. LOST requires a reason")
    no_reason = trader.call(
        "POST", f"/api/v1/deals/{deal_id}/transitions", {"to": "LOST"}, idempotency_key=key()
    )
    checks.check(
        "missing reason returns REASON_REQUIRED",
        no_reason.status == 422 and no_reason.code == "REASON_REQUIRED",
        f"HTTP {no_reason.status} {no_reason.code}",
    )

    # 13 ------------------------------------------------------------------
    checks.step("13. NEGOTIATION -> LOST with a reason")
    lost_key = key()
    lost_body = {"to": "LOST", "reason": "Verification: buyer withdrew the enquiry."}
    lost = trader.call(
        "POST", f"/api/v1/deals/{deal_id}/transitions", lost_body, idempotency_key=lost_key
    )
    checks.check(
        "deal is LOST and closed",
        lost.status == 200 and lost.body["status"] == "LOST" and lost.body["closed_at"] is not None,
        f"HTTP {lost.status}",
    )
    checks.check("no transitions remain", lost.body["allowed_transitions"] == [])
    checks.check(
        "reason is recorded on the deal",
        lost.body["transitions"][-1]["reason"] == "Verification: buyer withdrew the enquiry.",
    )


    # 14 ------------------------------------------------------------------
    checks.step("14. Replay and terminal-state protection")
    replay = trader.call(
        "POST", f"/api/v1/deals/{deal_id}/transitions", lost_body, idempotency_key=lost_key
    )
    checks.check(
        "replay is marked Idempotent-Replay",
        replay.status == 200 and replay.headers.get("idempotent-replay") == "true",
        replay.headers.get("idempotent-replay", ""),
    )
    checks.check(
        "replay returns the same version and status",
        replay.body["version"] == lost.body["version"] and replay.body["status"] == "LOST",
    )
    checks.check(
        "history did not grow",
        len(replay.body["transitions"]) == len(lost.body["transitions"]),
    )
    after_terminal = trader.call(
        "POST",
        f"/api/v1/deals/{deal_id}/transitions",
        {"to": "CANCELLED", "reason": "Should not be possible."},
        idempotency_key=key(),
    )
    checks.check(
        "a closed deal rejects further transitions",
        after_terminal.status == 409 and after_terminal.code == "INVALID_TRANSITION",
        f"HTTP {after_terminal.status} {after_terminal.code}",
    )

    # 15 ------------------------------------------------------------------
    checks.step("15. Cross-tenant isolation and dashboard")
    admin = connect(ADMIN_EMAIL, admin_password)
    foreign = admin.call("GET", f"/api/v1/deals/{deal_id}")
    checks.check(
        "foreign tenant gets 404 NOT_FOUND",
        foreign.status == 404 and foreign.code == "NOT_FOUND",
        f"HTTP {foreign.status} {foreign.code}",
    )
    admin_list = admin.call("GET", "/api/v1/deals?limit=100")
    admin_ids = [item["id"] for item in (admin_list.body or {}).get("items", [])]
    checks.check("foreign list excludes the deal", deal_id not in admin_ids)
    admin_write = admin.call(
        "POST",
        "/api/v1/counterparties",
        {"name": f"Admin attempt {reference}"},
        idempotency_key=key(),
    )
    checks.check(
        "admin cannot write trade data",
        admin_write.status == 403 and admin_write.code == "FORBIDDEN",
        f"HTTP {admin_write.status} {admin_write.code}",
    )
    dashboard = trader.call("GET", "/api/v1/dashboard/summary")
    activities = [entry["action"] for entry in (dashboard.body or {}).get("recent_activity", [])]
    checks.check(
        "dashboard is scoped to the trader company",
        dashboard.status == 200 and dashboard.body["company_id"] == company.get("company_id"),
    )
    checks.check("dashboard shows transition audit entries", "deal.transitioned" in activities)

    # Frontend ------------------------------------------------------------
    checks.step("Frontend server-rendered deal detail")
    try:
        with trader.opener.open(f"{FRONTEND_URL}/deals/{deal_id}", timeout=45) as response:
            html = response.read().decode("utf-8", errors="replace")
        checks.check("deal page returns 200", response.status == 200, f"HTTP {response.status}")
        checks.check("deal page renders the reference", reference in html)
        checks.check("deal page renders the terminal status", "Lost" in html)
    except (urllib.error.URLError, TimeoutError) as error:
        checks.check("deal page reachable", False, str(error))

    print("")
    if checks.failed:
        total = checks.passed + checks.failed
        print(f"TRADE WORKFLOW FAILED: {checks.failed} of {total} checks failed.")
        return 1
    print(f"TRADE WORKFLOW PASSED: {checks.passed} checks.")
    print(f"Deal {reference} ({deal_id}) in {company.get('name')}.")
    return 0


def main() -> int:
    try:
        return run()
    except RuntimeError as error:
        print(f"environment not ready: {error}", file=sys.stderr)
        return 2
    except urllib.error.URLError as error:
        print(f"API unreachable at {BASE_URL}: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover - manual verification entry point
    raise SystemExit(main())

