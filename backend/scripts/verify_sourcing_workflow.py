"""Stage 3 end-to-end sourcing workflow against a running local API.

Drives the real API with a real session cookie, CSRF token, idempotency keys and
If-Match versions: RFQ batch creation, the prepare/send gate, quote recording,
explicit FX, landed-cost calculation and recalculation, then the sales-quote
approval workflow including segregation of duties and revision superseding.

Passwords come from the environment (never argv):
``TOUCHE_VERIFY_STAGE3_TRADER_PASSWORD``, ``..._APPROVER_PASSWORD`` and
``..._OUTSIDER_PASSWORD``.

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
from datetime import UTC, datetime, timedelta
from typing import Any

BASE_URL = os.environ.get("TOUCHE_VERIFY_API", "http://127.0.0.1:8000")
FRONTEND_URL = os.environ.get("TOUCHE_VERIFY_WEB", "http://127.0.0.1:3000")
ORIGIN = os.environ.get("TOUCHE_VERIFY_ORIGIN", "http://localhost:3000")
TRADER_EMAIL = os.environ.get(
    "TOUCHE_VERIFY_STAGE3_TRADER_EMAIL", "stage3.trader@touche.example"
)
APPROVER_EMAIL = os.environ.get(
    "TOUCHE_VERIFY_STAGE3_APPROVER_EMAIL", "stage3.approver@touche.example"
)
OUTSIDER_EMAIL = os.environ.get(
    "TOUCHE_VERIFY_STAGE3_OUTSIDER_EMAIL", "stage3.outsider@touche.example"
)


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
        self.skipped = 0

    def check(self, name: str, condition: bool, detail: str = "") -> None:
        if condition:
            self.passed += 1
            print(f"  [pass] {name}")
        else:
            self.failed += 1
            print(f"  [FAIL] {name} {detail}".rstrip())

    def skip(self, name: str, reason: str) -> None:
        self.skipped += 1
        print(f"  [skip] {name} ({reason})")

    def step(self, title: str) -> None:
        print(f"\n==> {title}")


def require_env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value.strip():
        raise RuntimeError(f"{name} is not set")
    return value


def run() -> int:
    checks = Checks()
    trader = connect(TRADER_EMAIL, require_env("TOUCHE_VERIFY_STAGE3_TRADER_PASSWORD"))
    approver = connect(APPROVER_EMAIL, require_env("TOUCHE_VERIFY_STAGE3_APPROVER_PASSWORD"))
    outsider = connect(OUTSIDER_EMAIL, require_env("TOUCHE_VERIFY_STAGE3_OUTSIDER_PASSWORD"))

    checks.step("1. Trader session and permissions")
    checks.check("trader authenticated", trader.csrf is not None)
    checks.check("active company selected", bool(trader.company), str(trader.company))
    checks.check(
        "trader holds trade.write",
        "trade.write" in ((trader.company or {}).get("permissions") or []),
    )
    checks.check(
        "trader does not hold finance.approve",
        "finance.approve" not in ((trader.company or {}).get("permissions") or []),
    )
    checks.check(
        "approver holds finance.approve",
        "finance.approve" in ((approver.company or {}).get("permissions") or []),
    )

    stamp = datetime.now(tz=UTC).strftime("%H%M%S")
    checks.step("2. Master data (supplier, buyer, product, deal)")
    supplier = trader.call(
        "POST",
        "/api/v1/counterparties",
        {"name": f"Stage3 Supplier {stamp}", "type": "supplier", "country": "NL"},
        idempotency_key=key(),
    )
    checks.check("supplier created", supplier.status == 201, f"HTTP {supplier.status}")
    buyer = trader.call(
        "POST",
        "/api/v1/counterparties",
        {"name": f"Stage3 Buyer {stamp}", "type": "buyer", "country": "GB"},
        idempotency_key=key(),
    )
    checks.check("buyer created", buyer.status == 201, f"HTTP {buyer.status}")
    product = trader.call(
        "POST",
        "/api/v1/products",
        {
            "sku": f"S3-{stamp}",
            "name": "Stage 3 almonds",
            "unit": "kg",
            "currency": "USD",
            "unit_price": "2.0000",
        },
        idempotency_key=key(),
    )
    checks.check("product created", product.status == 201, f"HTTP {product.status}")
    product_id = str(product.body["id"])
    deal = trader.call(
        "POST",
        "/api/v1/deals",
        {
            "title": "Stage 3 verification deal",
            "counterparty_id": buyer.body["id"],
            "currency": "USD",
            "items": [{"product_id": product_id, "quantity": "100.000", "unit_price": "2.0000"}],
        },
        idempotency_key=key(),
    )
    checks.check("deal created", deal.status == 201, f"HTTP {deal.status}")

    checks.step("3. One RFQ per supplier")
    rfq = trader.call(
        "POST",
        "/api/v1/rfqs",
        {
            "deal_id": deal.body["id"],
            "supplier_ids": [supplier.body["id"]],
            "requested_currency": "USD",
            "delivery_location": "Rotterdam, NL",
            "items": [
                {
                    "product_id": product_id,
                    "description": "Almond kernels, 25 kg bags",
                    "quantity": "100.000",
                    "unit": "kg",
                }
            ],
        },
        idempotency_key=key(),
    )
    checks.check("RFQ batch created", rfq.status == 201, f"HTTP {rfq.status} {rfq.body}")
    rfq_body = (rfq.body or {}).get("items", [{}])[0]
    rfq_path = f"/api/v1/rfqs/{rfq_body.get('id')}"
    checks.check("one RFQ returned", len((rfq.body or {}).get("items", [])) == 1)
    checks.check("RFQ starts as DRAFT", rfq_body.get("status") == "DRAFT")
    checks.check(
        "reference generated",
        str(rfq_body.get("reference_number", "")).startswith("RFQ-"),
    )

    checks.step("4. PREPARED is not SENT")
    skipped = trader.call(
        "POST",
        f"{rfq_path}/transitions",
        {"to": "SENT", "channel": "email", "evidence": "message-id:<stage3@touche>"},
        idempotency_key=key(),
    )
    checks.check(
        "cannot jump from DRAFT to SENT",
        skipped.status == 409 and skipped.code == "INVALID_TRANSITION",
        f"HTTP {skipped.status} {skipped.code}",
    )
    no_key = trader.call("POST", f"{rfq_path}/transitions", {"to": "PREPARED"})
    checks.check(
        "transition requires an Idempotency-Key",
        no_key.status == 400 and no_key.code == "IDEMPOTENCY_KEY_REQUIRED",
        f"HTTP {no_key.status} {no_key.code}",
    )
    prepared = trader.call(
        "POST", f"{rfq_path}/transitions", {"to": "PREPARED"}, idempotency_key=key()
    )
    checks.check(
        "prepare succeeds",
        prepared.status == 200 and (prepared.body or {}).get("status") == "PREPARED",
        f"HTTP {prepared.status}",
    )
    snapshot = trader.call("GET", f"{rfq_path}/revisions/1")
    checks.check("prepared snapshot stored", snapshot.status == 200, f"HTTP {snapshot.status}")
    checks.check(
        "snapshot contains the requested line",
        (snapshot.body or {}).get("snapshot", {}).get("items", [{}])[0].get("product_id")
        == product_id,
    )
    no_evidence = trader.call(
        "POST", f"{rfq_path}/transitions", {"to": "SENT", "channel": "email"}, idempotency_key=key()
    )
    checks.check(
        "send without evidence rejected",
        no_evidence.status == 400 and no_evidence.code == "BAD_REQUEST",
        f"HTTP {no_evidence.status} {no_evidence.code}",
    )
    sent = trader.call(
        "POST",
        f"{rfq_path}/transitions",
        {"to": "SENT", "channel": "email", "evidence": "message-id:<stage3@touche>"},
        idempotency_key=key(),
    )
    checks.check(
        "send with evidence succeeds",
        sent.status == 200
        and (sent.body or {}).get("status") == "SENT"
        and (sent.body or {}).get("sent_at") is not None,
        f"HTTP {sent.status}",
    )


    checks.step("5. Record a supplier quote")
    valid_until = (datetime.now(tz=UTC) + timedelta(days=30)).date().isoformat()
    quote = trader.call(
        "POST",
        f"{rfq_path}/quotes",
        {
            "currency": "EUR",
            "incoterm": "CIF",
            "named_delivery_place": "Rotterdam, NL",
            "payment_terms": "30 days net",
            "lead_time_days": 21,
            "valid_until": valid_until,
            "source_reference": "email: stage 3 supplier quote",
            "items": [{"product_id": product_id, "quantity": "100.000", "unit_price": "1.6000"}],
        },
        idempotency_key=key(),
    )
    checks.check("quote recorded", quote.status == 201, f"HTTP {quote.status}")
    quote_body = quote.body or {}
    checks.check("quote total is 160.00 EUR", quote_body.get("total_value") == "160.00")
    checks.check("quote currency is EUR", quote_body.get("currency") == "EUR")
    checks.check("quote revision is 1", quote_body.get("revision") == 1)
    rfq_after_quote = trader.call("GET", rfq_path)
    checks.check(
        "RFQ moved to RESPONDED",
        (rfq_after_quote.body or {}).get("status") == "RESPONDED",
        str((rfq_after_quote.body or {}).get("status")),
    )

    checks.step("6. Pricing requires explicit FX")
    no_fx = trader.call(
        "POST",
        "/api/v1/pricing-scenarios",
        {"supplier_quote_id": quote_body.get("id"), "target_currency": "USD", "margin_pct": "20"},
        idempotency_key=key(),
    )
    checks.check(
        "cross-currency pricing blocked without a snapshot",
        no_fx.status == 400 and no_fx.code == "BAD_REQUEST",
        f"HTTP {no_fx.status} {no_fx.code}",
    )
    fx = trader.call(
        "POST",
        "/api/v1/fx-rates",
        {
            "base_currency": "EUR",
            "quote_currency": "USD",
            "rate": "1.1000000000",
            # Unique per run: the pair and effective time are unique per company.
            "effective_at": datetime.now(tz=UTC).isoformat(),
            "source": f"ECB reference rate {stamp}",
        },
        idempotency_key=key(),
    )
    checks.check("FX snapshot recorded", fx.status == 201, f"HTTP {fx.status} {fx.body}")

    checks.step("7. Deterministic landed cost")
    scenario = trader.call(
        "POST",
        "/api/v1/pricing-scenarios",
        {
            "supplier_quote_id": quote_body.get("id"),
            "target_currency": "USD",
            "margin_pct": "20",
            "fx_rate_snapshot_id": fx.body["id"],
            "components": [
                {
                    "cost_type": "FREIGHT",
                    "amount": "40.00",
                    "currency": "USD",
                    "basis": "ORDER",
                    "source_reference": "freight invoice STAGE3",
                    "verification_status": "VERIFIED",
                }
            ],
        },
        idempotency_key=key(),
    )
    checks.check(
        "scenario created", scenario.status == 201, f"HTTP {scenario.status} {scenario.body}"
    )
    scenario_body = scenario.body or {}
    scenario_path = f"/api/v1/pricing-scenarios/{scenario_body.get('id')}"
    totals = (scenario_body.get("calculated_results") or {}).get("totals", {})
    checks.check(
        "purchase converted at 1.10", totals.get("purchase_total") == "176.00", str(totals)
    )
    checks.check("landed total includes freight", totals.get("landed_total") == "216.00")
    checks.check("status is VERIFIED_INPUTS", scenario_body.get("status") == "VERIFIED_INPUTS")
    checks.check("calculation version stored", bool(scenario_body.get("calculation_version")))
    checks.check(
        "order cost allocated to the single line",
        (scenario_body.get("calculated_results") or {}).get("lines", [{}])[0].get("allocated_cost")
        == "40.00",
    )

    checks.step("8. Recalculation is explicit and versioned")
    recalculation = {
        "supplier_quote_id": quote_body.get("id"),
        "target_currency": "USD",
        "margin_pct": "20",
        "fx_rate_snapshot_id": fx.body["id"],
        "components": [
            {
                "cost_type": "FREIGHT",
                "amount": "60.00",
                "currency": "USD",
                "basis": "ORDER",
                "source_reference": "freight invoice STAGE3b",
                "verification_status": "VERIFIED",
            }
        ],
    }
    stale = trader.call(
        "PUT",
        scenario_path,
        recalculation,
        idempotency_key=key(),
        if_match='"v99"',
    )
    checks.check(
        "stale If-Match is a version conflict",
        stale.status == 409 and stale.code == "VERSION_CONFLICT",
    )
    recalculated = trader.call(
        "PUT", scenario_path, recalculation, idempotency_key=key(), if_match='"v1"'
    )
    checks.check(
        "recalculation succeeds and versions up",
        recalculated.status == 200 and (recalculated.body or {}).get("version") == 2,
        f"HTTP {recalculated.status}",
    )
    checks.check(
        "new landed total reflects the new freight",
        ((recalculated.body or {}).get("calculated_results") or {}).get("totals", {}).get(
            "landed_total"
        )
        == "236.00",
    )


    checks.step("9. Sales quote workflow and separation of duties")
    sales_quote = trader.call(
        "POST",
        "/api/v1/sales-quotes",
        {
            "scenario_id": scenario_body.get("id"),
            "customer_id": buyer.body["id"],
            "valid_until": valid_until,
            "incoterm": "CIF",
            "named_delivery_place": "Rotterdam, NL",
            "payment_terms": "30 days net",
        },
        idempotency_key=key(),
    )
    checks.check("sales quote drafted", sales_quote.status == 201, f"HTTP {sales_quote.status}")
    sales_body = sales_quote.body or {}
    sales_path = f"/api/v1/sales-quotes/{sales_body.get('id')}"
    checks.check("sales quote starts in DRAFT", sales_body.get("status") == "DRAFT")
    checks.check(
        "sales total is the recomputed scenario value",
        sales_body.get("total_value") == "295.00",
        str(sales_body.get("total_value")),
    )

    submitted = trader.call(
        "POST", f"{sales_path}/submit", {}, idempotency_key=key(), if_match='"v1"'
    )
    checks.check(
        "submitted for approval",
        submitted.status == 200 and (submitted.body or {}).get("status") == "PENDING_APPROVAL",
        f"HTTP {submitted.status} {submitted.code}",
    )
    trader_approval = trader.call(
        "POST", f"{sales_path}/approve", {}, idempotency_key=key(), if_match='"v2"'
    )
    checks.check(
        "trader cannot approve (no finance.approve)",
        trader_approval.status == 403 and trader_approval.code == "FORBIDDEN",
        f"HTTP {trader_approval.status} {trader_approval.code}",
    )
    approved = approver.call(
        "POST", f"{sales_path}/approve", {}, idempotency_key=key(), if_match='"v2"'
    )
    checks.check(
        "approver approves",
        approved.status == 200 and (approved.body or {}).get("status") == "APPROVED",
        f"HTTP {approved.status} {approved.code}",
    )
    checks.check(
        "approval pair recorded",
        bool((approved.body or {}).get("approved_by"))
        and bool((approved.body or {}).get("approved_at")),
    )
    checks.check(
        "approved quote has no transitions left",
        (approved.body or {}).get("allowed_transitions") == [],
    )

    revised = trader.call(
        "POST",
        f"{sales_path}/revisions",
        {"valid_until": valid_until, "reason": "Customer asked for a longer validity"},
        idempotency_key=key(),
        if_match='"v3"',
    )
    checks.check(
        "revision drafted from the approved quote",
        revised.status == 201
        and (revised.body or {}).get("revision") == 2
        and (revised.body or {}).get("status") == "DRAFT",
        f"HTTP {revised.status} {revised.body}",
    )
    original = trader.call("GET", sales_path)
    checks.check(
        "original approval is intact and superseded",
        (original.body or {}).get("status") == "APPROVED"
        and (original.body or {}).get("superseded_by_sales_quote_id")
        == (revised.body or {}).get("id"),
    )

    checks.step("10. Tenant isolation")
    foreign_rfq = outsider.call("GET", rfq_path)
    checks.check(
        "another company cannot read the RFQ",
        foreign_rfq.status == 404 and foreign_rfq.code == "NOT_FOUND",
        f"HTTP {foreign_rfq.status}",
    )
    foreign_list = outsider.call("GET", "/api/v1/rfqs")
    checks.check(
        "another company's RFQ list is empty",
        foreign_list.status == 200 and (foreign_list.body or {}).get("items") == [],
    )

    checks.step("11. Frontend renders the sourcing pages")
    for path, marker in (
        ("/rfq", "Supplier requests"),
        ("/quotes", "Supplier quotes"),
        ("/pricing", "Landed-cost scenarios"),
        ("/sales-quotes", "Customer quotations"),
        ("/fx-rates", "FX snapshots"),
    ):
        try:
            request = urllib.request.Request(  # noqa: S310 - fixed local URL
                f"{FRONTEND_URL}{path}", headers={"Accept": "text/html"}
            )
            with trader.opener.open(request, timeout=20) as response:
                html = response.read().decode("utf-8", errors="replace")
            checks.check(
                f"{path} rendered for the trader", response.status == 200 and marker in html
            )
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            checks.skip(f"{path} rendered", f"frontend unreachable: {error}")


    print(
        f"\nSummary: {checks.passed} passed, {checks.failed} failed, {checks.skipped} skipped"
    )
    return 0 if checks.failed == 0 else 1


def main() -> int:
    if not _api_reachable():
        print(f"API is not reachable at {BASE_URL}", file=sys.stderr)
        return 2
    try:
        return run()
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 2


def _api_reachable() -> bool:
    try:
        with urllib.request.urlopen(  # noqa: S310 - fixed local URL
            f"{BASE_URL}/api/v1/health/live", timeout=5
        ) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


if __name__ == "__main__":
    raise SystemExit(main())

