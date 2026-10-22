"""Stage 4 end-to-end operations workflow against a running local stack.

Drives the real API with a real session cookie, CSRF token, idempotency keys and
If-Match versions, then renders the real Next.js pages with that same session.

Passwords come from the environment (never argv):
``TOUCHE_VERIFY_STAGE4_TRADER_PASSWORD``, ``..._APPROVER_PASSWORD`` and
``..._OUTSIDER_PASSWORD``.

Exit code 0 means every check passed; 1 means at least one check failed; 2 means
the environment was not prepared.
"""

from __future__ import annotations

import hashlib
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

TRADER_EMAIL = os.environ.get("TOUCHE_VERIFY_STAGE4_TRADER_EMAIL", "stage4.trader@touche.example")
APPROVER_EMAIL = os.environ.get(
    "TOUCHE_VERIFY_STAGE4_APPROVER_EMAIL", "stage4.approver@touche.example"
)
OUTSIDER_EMAIL = os.environ.get(
    "TOUCHE_VERIFY_STAGE4_OUTSIDER_EMAIL", "stage4.outsider@touche.example"
)

PASSED: list[str] = []
FAILED: list[str] = []


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

    @property
    def details(self) -> Any:
        if isinstance(self.body, dict):
            error = self.body.get("error")
            if isinstance(error, dict):
                return error.get("details")
        return None


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
        request.add_header("Origin", ORIGIN)
        if self.csrf and not anonymous:
            request.add_header("X-CSRF-Token", self.csrf)
        if idempotency_key:
            request.add_header("Idempotency-Key", idempotency_key)
        if if_match:
            request.add_header("If-Match", if_match)
        return self._send(request)

    def _send(self, request: urllib.request.Request) -> Response:
        try:
            with self.opener.open(request, timeout=30) as response:
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

    def page(self, path: str) -> Response:
        request = urllib.request.Request(f"{FRONTEND_URL}{path}")  # noqa: S310
        request.add_header("Accept", "text/html")
        try:
            with self.opener.open(request, timeout=90) as response:
                return Response(
                    status=response.status,
                    body=response.read().decode("utf-8", errors="replace"),
                    headers={key.lower(): value for key, value in response.headers.items()},
                )
        except urllib.error.HTTPError as error:
            return Response(
                status=error.code,
                body=error.read().decode("utf-8", errors="replace"),
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


def check(label: str, condition: bool, detail: str = "") -> bool:
    if condition:
        PASSED.append(label)
        print(f"  PASS  {label}")
    else:
        FAILED.append(label)
        print(f"  FAIL  {label}{f' â€” {detail}' if detail else ''}")
    return condition


def future(days: int = 30) -> str:
    return str((datetime.now(tz=UTC) + timedelta(days=days)).date())


def etag(version: int) -> str:
    return f'"v{version}"'


def connect(email: str, password: str, company_name: str) -> Client:
    client = new_client()
    login = client.call(
        "POST", "/api/v1/auth/login", {"email": email, "password": password}, anonymous=True
    )
    if login.status != 200:
        raise RuntimeError(f"login failed for {email}: HTTP {login.status} {login.body}")
    client.csrf = str(login.body["session"]["csrf_token"])
    client.company = login.body["session"]["company"]

    if client.company is None:
        companies = client.call("GET", "/api/v1/session/companies")
        target = next(
            (
                item
                for item in companies.body.get("companies", [])
                if item.get("name") == company_name
            ),
            None,
        )
        if target is None:
            raise RuntimeError(f"{email} has no membership in {company_name}")
        switched = client.call(
            "POST", "/api/v1/session/company", {"company_id": target["company_id"]}
        )
        if switched.status != 200:
            raise RuntimeError(f"cannot switch company: {switched.status} {switched.body}")
        client.csrf = str(switched.body["session"]["csrf_token"])
        client.company = switched.body["session"]["company"]
    return client


def upload_document(
    client: Client,
    *,
    fields: dict[str, str],
    filename: str,
    content: bytes,
    mime_type: str,
    idempotency_key: str | None = None,
) -> Response:
    boundary = f"----touche{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.append(
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
                f"{value}\r\n"
            ).encode()
        )
    chunks.append(
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
            f'filename="{filename}"\r\nContent-Type: {mime_type}\r\n\r\n'
        ).encode()
    )
    chunks.append(content)
    chunks.append(f"\r\n--{boundary}--\r\n".encode())

    request = urllib.request.Request(  # noqa: S310
        f"{BASE_URL}/api/v1/documents", data=b"".join(chunks), method="POST"
    )
    request.add_header("Accept", "application/json")
    request.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    request.add_header("Origin", ORIGIN)
    if client.csrf:
        request.add_header("X-CSRF-Token", client.csrf)
    request.add_header("Idempotency-Key", idempotency_key or uuid.uuid4().hex)
    return client._send(request)  # noqa: SLF001 - same module


def post(
    client: Client,
    path: str,
    body: Any | None = None,
    *,
    if_match: str | None = None,
    key: str | None = None,
) -> Response:
    return client.call(
        "POST",
        path,
        body if body is not None else {},
        idempotency_key=key or uuid.uuid4().hex,
        if_match=if_match,
    )


def sees_no_records(client: Client, path: str) -> bool:
    """True when the list endpoint answers normally with an empty page."""
    response = client.call("GET", path)
    return response.status == 200 and not (response.body or {}).get("items")


def must(label: str, response: Response, status: int = 201) -> dict[str, Any]:
    """Fail loudly with the API's own message when a prerequisite step breaks."""
    if response.status != status:
        print(f"{label} failed: {response.status} {response.body}", file=sys.stderr)
        raise SystemExit(2)
    return dict(response.body)


def main() -> int:
    passwords = {
        "trader": os.environ.get("TOUCHE_VERIFY_STAGE4_TRADER_PASSWORD"),
        "approver": os.environ.get("TOUCHE_VERIFY_STAGE4_APPROVER_PASSWORD"),
        "outsider": os.environ.get("TOUCHE_VERIFY_STAGE4_OUTSIDER_PASSWORD"),
    }
    if not all(passwords.values()):
        print(
            "Set TOUCHE_VERIFY_STAGE4_{TRADER,APPROVER,OUTSIDER}_PASSWORD before running.",
            file=sys.stderr,
        )
        return 2

    try:
        trader = connect(TRADER_EMAIL, str(passwords["trader"]), "Stage 4 Trading")
        approver = connect(APPROVER_EMAIL, str(passwords["approver"]), "Stage 4 Trading")
        outsider = connect(OUTSIDER_EMAIL, str(passwords["outsider"]), "Stage 4 Outsider")
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 2

    permissions = trader.company.get("permissions", []) if trader.company else []
    approver_permissions = approver.company.get("permissions", []) if approver.company else []
    check("trader holds trade.write", "trade.write" in permissions)
    check("approver holds finance.approve", "finance.approve" in approver_permissions)
    check(
        "outsider belongs to a different company",
        bool(trader.company and outsider.company)
        and trader.company["company_id"] != outsider.company["company_id"],
    )

    suffix = uuid.uuid4().hex[:6].upper()
    supplier = post(
        trader,
        "/api/v1/counterparties",
        {"name": f"Stage 4 Supplier {suffix}", "type": "supplier", "country": "AE"},
    )
    buyer = post(
        trader,
        "/api/v1/counterparties",
        {"name": f"Stage 4 Buyer {suffix}", "type": "buyer", "country": "NL"},
    )
    product = post(
        trader,
        "/api/v1/products",
        {
            "sku": f"S4-{suffix}",
            "name": f"Stage 4 cocoa {suffix}",
            "unit": "kg",
            "currency": "USD",
            "unit_price": "2.0000",
        },
    )
    if not (supplier.status == 201 and buyer.status == 201 and product.status == 201):
        print("Could not create the counterparties/product for the workflow.", file=sys.stderr)
        return 2

    deal_response = post(
        trader,
        "/api/v1/deals",
        {
            "title": f"Stage 4 deal {suffix}",
            "counterparty_id": buyer.body["id"],
            "currency": "USD",
            "items": [
                {
                    "product_id": product.body["id"],
                    "quantity": "100.000",
                    "unit_price": "2.0000",
                }
            ],
        },
    )
    deal = deal_response.body
    opened = post(
        trader,
        f"/api/v1/deals/{deal['id']}/transitions",
        {"to": "OPEN"},
        if_match=etag(int(deal["version"])),
    )
    deal = opened.body
    check("deal opened for execution", opened.status == 200, str(opened.body))

    rfq = post(
        trader,
        "/api/v1/rfqs",
        {
            "deal_id": deal["id"],
            "supplier_ids": [supplier.body["id"]],
            "requested_currency": "USD",
            "delivery_location": "Rotterdam, NL",
            "response_due_date": future(),
            "items": [
                {
                    "product_id": product.body["id"],
                    "description": "Cocoa beans, 25 kg bags",
                    "quantity": "100.000",
                    "unit": "kg",
                }
            ],
        },
    )
    rfq_row = must("RFQ creation", rfq)["items"][0]
    prepared = must(
        "RFQ preparation",
        post(
            trader,
            f"/api/v1/rfqs/{rfq_row['id']}/transitions",
            {"to": "PREPARED"},
            if_match=etag(int(rfq_row["version"])),
        ),
        200,
    )
    must(
        "RFQ send",
        post(
            trader,
            f"/api/v1/rfqs/{rfq_row['id']}/transitions",
            {"to": "SENT", "channel": "email", "evidence": "email: rfq sent from the desk"},
            if_match=etag(int(prepared["version"])),
        ),
        200,
    )
    quote = must(
        "Supplier quote recording",
        post(
            trader,
            f"/api/v1/rfqs/{rfq_row['id']}/quotes",
            {
                "currency": "USD",
                "incoterm": "CIF",
                "named_delivery_place": "Rotterdam, NL",
                "payment_terms": "30 days net",
                "lead_time_days": 21,
                "valid_until": future(),
                "source_reference": "email: supplier quote",
                "items": [
                    {
                        "product_id": product.body["id"],
                        "quantity": "100.000",
                        "unit_price": "1.6000",
                    }
                ],
            },
        ),
    )
    scenario = must(
        "Pricing scenario",
        post(
            trader,
            "/api/v1/pricing-scenarios",
            {
                "supplier_quote_id": quote["id"],
                "target_currency": "USD",
                "margin_pct": "20",
                "components": [
                    {
                        "cost_type": "FREIGHT",
                        "amount": "40.00",
                        "currency": "USD",
                        "basis": "ORDER",
                        "source_reference": "freight quote",
                        "verification_status": "VERIFIED",
                    }
                ],
            },
        ),
    )
    sales_quote = must(
        "Sales quote draft",
        post(
            trader,
            "/api/v1/sales-quotes",
            {
                "scenario_id": scenario["id"],
                "customer_id": buyer.body["id"],
                "valid_until": future(),
                "incoterm": "CIF",
                "named_delivery_place": "Rotterdam, NL",
                "payment_terms": "30 days net",
            },
        ),
    )
    submitted = must(
        "Sales quote submission",
        post(
            trader,
            f"/api/v1/sales-quotes/{sales_quote['id']}/submit",
            {},
            if_match=etag(int(sales_quote["version"])),
        ),
        200,
    )
    approved = must(
        "Sales quote approval",
        post(
            approver,
            f"/api/v1/sales-quotes/{sales_quote['id']}/approve",
            {},
            if_match=etag(int(submitted["version"])),
        ),
        200,
    )
    check(
        "approved quote revision ready for acceptance",
        approved["status"] == "APPROVED",
        str(approved),
    )
    before_orders = trader.call("GET", f"/api/v1/sales-orders?deal_id={deal['id']}")
    check(
        "internal approval alone creates no order",
        before_orders.status == 200 and not before_orders.body.get("items"),
        f"{before_orders.status} {str(before_orders.body)[:200]}",
    )

    refused = post(
        trader,
        f"/api/v1/deals/{deal['id']}/sales-order",
        {"sales_quote_id": approved["id"]},
    )
    check(
        "conversion without acceptance is refused",
        refused.status == 422 and refused.code == "VALIDATION_ERROR",
        f"{refused.status} {refused.body}",
    )

    direct = post(
        trader,
        f"/api/v1/deals/{deal['id']}/transitions",
        {"to": "WON"},
        if_match=etag(int(deal["version"])),
    )
    check(
        "WON cannot be set by a direct deal transition",
        direct.status == 409 and direct.code == "TRANSITION_DISABLED",
        f"{direct.status} {direct.code}",
    )

    acceptance = post(
        trader,
        f"/api/v1/deals/{deal['id']}/customer-acceptance",
        {
            "channel": "SIGNED_QUOTE",
            "accepted_at": datetime.now(tz=UTC).isoformat(),
            "accepted_by_name": "Dana Buyer",
            "evidence_reference": f"signed quote {suffix}",
        },
    )
    check(
        "customer acceptance recorded with evidence",
        acceptance.status == 201,
        str(acceptance.body),
    )

    conversion_key = f"stage4-{suffix}"
    converted = post(
        trader,
        f"/api/v1/deals/{deal['id']}/sales-order",
        {
            "sales_quote_id": approved["id"],
            "acceptance_evidence_id": acceptance.body["id"],
        },
        key=conversion_key,
    )
    order = converted.body
    check("conversion creates the order", converted.status == 201, str(converted.body))
    deal_after = trader.call("GET", f"/api/v1/deals/{deal['id']}").body
    check("deal becomes WON in the same transaction", deal_after["status"] == "WON")
    check(
        "order stores the accepted revision and total",
        order.get("sales_quote_revision") == approved["revision"]
        and order.get("order_total") == approved["total_value"],
        f"{order.get('sales_quote_revision')} {order.get('order_total')}",
    )
    snapshot = order.get("accepted_terms", {})
    check(
        "accepted commercial snapshot is preserved",
        snapshot.get("sales_quote_id") == approved["id"]
        and snapshot.get("acceptance_evidence_id") == acceptance.body["id"]
        and snapshot.get("items", [{}])[0].get("unit_price")
        == approved["items"][0]["unit_price"],
    )

    replay = post(
        trader,
        f"/api/v1/deals/{deal['id']}/sales-order",
        {
            "sales_quote_id": approved["id"],
            "acceptance_evidence_id": acceptance.body["id"],
        },
        key=conversion_key,
    )
    check(
        "same idempotency key replays the original order",
        replay.status == 201
        and replay.body["id"] == order["id"]
        and replay.headers.get("idempotent-replay") == "true",
        f"{replay.status} {replay.headers.get('idempotent-replay')}",
    )

    duplicate = post(
        trader,
        f"/api/v1/deals/{deal['id']}/sales-order",
        {
            "sales_quote_id": approved["id"],
            "acceptance_evidence_id": acceptance.body["id"],
        },
        key=f"stage4-other-{suffix}",
    )
    check(
        "a different key after WON is refused",
        duplicate.status == 409 and duplicate.code == "ALREADY_WON",
        f"{duplicate.status} {duplicate.code}",
    )
    listing = trader.call("GET", f"/api/v1/sales-orders?deal_id={deal['id']}")
    check(
        "exactly one order exists for the deal",
        listing.status == 200 and len(listing.body.get("items") or []) == 1,
        f"{listing.status} {str(listing.body)[:200]}",
    )

    purchase_order = post(
        trader,
        "/api/v1/purchase-orders",
        {
            "sales_order_id": order["id"],
            "supplier_id": supplier.body["id"],
            "supplier_quote_id": quote["id"],
            "incoterm": "CIF",
            "named_delivery_place": "Rotterdam, NL",
            "payment_terms": "30 days net",
            "items": [
                {
                    "product_id": product.body["id"],
                    "quantity": "100.000",
                    "unit": "kg",
                    "unit_cost": "1.6000",
                }
            ],
        },
    )
    po = purchase_order.body
    check(
        "supplier purchase order starts as a draft",
        purchase_order.status == 201 and po["status"] == "DRAFT",
        str(purchase_order.body),
    )

    by_trader = post(
        trader,
        f"/api/v1/purchase-orders/{po['id']}/transitions",
        {"target": "APPROVED"},
        if_match=etag(int(po["version"])),
    )
    check(
        "a trader cannot approve a purchase order",
        by_trader.status == 403,
        f"{by_trader.status} {by_trader.code}",
    )

    po_approved = post(
        approver,
        f"/api/v1/purchase-orders/{po['id']}/transitions",
        {"target": "APPROVED"},
        if_match=etag(int(po["version"])),
    )
    check(
        "an approver approves the purchase order",
        po_approved.status == 200 and po_approved.body["status"] == "APPROVED",
        str(po_approved.body),
    )

    no_evidence = post(
        trader,
        f"/api/v1/purchase-orders/{po['id']}/transitions",
        {"target": "RECORDED_SENT"},
        if_match=etag(int(po_approved.body["version"])),
    )
    check(
        "recording a send without channel and reference is refused",
        no_evidence.status == 400,
        f"{no_evidence.status} {no_evidence.body}",
    )

    recorded = post(
        trader,
        f"/api/v1/purchase-orders/{po['id']}/transitions",
        {
            "target": "RECORDED_SENT",
            "dispatch_channel": "EMAIL",
            "dispatch_reference": f"SMTP-{suffix}",
        },
        if_match=etag(int(po_approved.body["version"])),
    )
    check(
        "the send is recorded with its external reference",
        recorded.status == 200
        and recorded.body["status"] == "RECORDED_SENT"
        and recorded.body["dispatch_channel"] == "EMAIL",
        str(recorded.body),
    )

    confirmed = post(
        trader,
        f"/api/v1/purchase-orders/{po['id']}/transitions",
        {
            "target": "SUPPLIER_CONFIRMED",
            "supplier_confirmation_reference": f"SUP-ACK-{suffix}",
            "evidence_reference": "email: supplier acknowledgement",
        },
        if_match=etag(int(recorded.body["version"])),
    )
    check(
        "supplier confirmation requires and stores its evidence",
        confirmed.status == 200 and confirmed.body["supplier_confirmed_at"] is not None,
        str(confirmed.body),
    )

    order_item_id = order["items"][0]["id"]
    planned = post(
        trader,
        "/api/v1/shipments",
        {
            "sales_order_id": order["id"],
            "transport_mode": "SEA",
            "origin": "Jebel Ali, AE",
            "destination": "Rotterdam, NL",
            "carrier": "Maersk",
            "forwarder": "Kuehne+Nagel",
            "planned_dispatch_at": (datetime.now(tz=UTC) + timedelta(days=3)).isoformat(),
            "estimated_arrival_at": (datetime.now(tz=UTC) + timedelta(days=21)).isoformat(),
            "items": [{"sales_order_item_id": order_item_id, "quantity": "40.000"}],
        },
    )
    shipment = planned.body
    check(
        "a partial shipment is planned against real order quantities",
        planned.status == 201 and shipment["status"] == "PLANNED",
        str(planned.body),
    )

    over = post(
        trader,
        "/api/v1/shipments",
        {
            "sales_order_id": order["id"],
            "transport_mode": "SEA",
            "origin": "Jebel Ali, AE",
            "destination": "Rotterdam, NL",
            "items": [{"sales_order_item_id": order_item_id, "quantity": "61.000"}],
        },
    )
    check(
        "over-allocation beyond the outstanding quantity is refused",
        over.status == 400,
        f"{over.status} {over.body}",
    )

    booked = post(
        trader,
        f"/api/v1/shipments/{shipment['id']}/transitions",
        {"target": "BOOKED"},
        if_match=etag(int(shipment["version"])),
    )
    check("shipment booked", booked.status == 200, str(booked.body))

    no_tracking = post(
        trader,
        f"/api/v1/shipments/{shipment['id']}/transitions",
        {"target": "DISPATCHED"},
        if_match=etag(int(booked.body["version"])),
    )
    check(
        "dispatch without a booking reference is refused",
        no_tracking.status == 400,
        f"{no_tracking.status} {no_tracking.body}",
    )

    dispatched = post(
        trader,
        f"/api/v1/shipments/{shipment['id']}/transitions",
        {
            "target": "DISPATCHED",
            "tracking_reference": f"MSKU{suffix}",
            "tracking_source": "MANUAL",
        },
        if_match=etag(int(booked.body["version"])),
    )
    check(
        "dispatch is recorded with manual tracking provenance",
        dispatched.status == 200,
        str(dispatched.body),
    )

    in_transit = post(
        trader,
        f"/api/v1/shipments/{shipment['id']}/transitions",
        {"target": "IN_TRANSIT"},
        if_match=etag(int(dispatched.body["version"])),
    )
    arrived = post(
        trader,
        f"/api/v1/shipments/{shipment['id']}/transitions",
        {"target": "ARRIVED"},
        if_match=etag(int(in_transit.body["version"])),
    )
    check(
        "arrival records the actual timestamp, not the ETA",
        arrived.status == 200 and arrived.body["actual_arrival_at"] is not None,
        str(arrived.body),
    )

    no_delivery = post(
        trader,
        f"/api/v1/shipments/{shipment['id']}/transitions",
        {"target": "DELIVERED"},
        if_match=etag(int(arrived.body["version"])),
    )
    check(
        "delivery without evidence is refused",
        no_delivery.status == 400,
        f"{no_delivery.status} {no_delivery.body}",
    )

    delivered = post(
        trader,
        f"/api/v1/shipments/{shipment['id']}/transitions",
        {"target": "DELIVERED", "delivery_evidence_reference": f"POD-{suffix}"},
        if_match=etag(int(arrived.body["version"])),
    )
    check(
        "delivery is recorded with its evidence reference",
        delivered.status == 200 and delivered.body["delivered_at"] is not None,
        str(delivered.body),
    )

    post(
        trader,
        f"/api/v1/shipments/{shipment['id']}/costs",
        {
            "cost_type": "FREIGHT",
            "stage": "INCURRED",
            "amount": "512.50",
            "currency": "USD",
            "reference": f"INV-{suffix}",
        },
    )
    post(
        trader,
        f"/api/v1/shipments/{shipment['id']}/references",
        {
            "reference_type": "CONTAINER",
            "reference_value": f"MSKU{suffix}",
            "provenance": "DOCUMENT_EVIDENCE",
        },
    )
    refreshed = trader.call("GET", f"/api/v1/shipments/{shipment['id']}").body
    check(
        "logistics costs keep their own stage",
        any(cost["stage"] == "INCURRED" for cost in refreshed["costs"]),
    )

    fulfilment = trader.call("GET", f"/api/v1/sales-orders/{order['id']}/fulfilment").body
    line = fulfilment["lines"][0]
    check(
        "a 40 of 100 delivery does not fulfil the order",
        line["delivered"] == "40.000"
        and line["remaining"] == "60.000"
        and fulfilment["fully_delivered"] is False,
        str(fulfilment),
    )
    check(
        "the order moves to in-fulfilment, not fulfilled",
        trader.call("GET", f"/api/v1/sales-orders/{order['id']}").body["status"]
        == "IN_FULFILLMENT",
    )

    second = post(
        trader,
        "/api/v1/shipments",
        {
            "sales_order_id": order["id"],
            "transport_mode": "SEA",
            "origin": "Jebel Ali, AE",
            "destination": "Rotterdam, NL",
            "items": [{"sales_order_item_id": order_item_id, "quantity": "60.000"}],
        },
    )
    second_id = second.body["id"]
    for target, extra in (
        ("BOOKED", {}),
        (
            "DISPATCHED",
            {"tracking_reference": f"MSKU{suffix}-B", "tracking_source": "MANUAL"},
        ),
        ("IN_TRANSIT", {}),
        ("ARRIVED", {}),
        ("DELIVERED", {"delivery_evidence_reference": f"POD-{suffix}-B"}),
    ):
        current = trader.call("GET", f"/api/v1/shipments/{second_id}").body
        post(
            trader,
            f"/api/v1/shipments/{second_id}/transitions",
            {"target": target, **extra},
            if_match=etag(int(current["version"])),
        )
    final = trader.call("GET", f"/api/v1/sales-orders/{order['id']}").body
    check(
        "completing the remaining quantity fulfils the order",
        final["status"] == "FULFILLED",
        final["status"],
    )

    pdf = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n%%EOF\n"
    uploaded = upload_document(
        trader,
        fields={
            "document_type": "DELIVERY_CONFIRMATION",
            "linked_entity_type": "SHIPMENT",
            "linked_entity_id": shipment["id"],
            "title": "Signed proof of delivery",
        },
        filename="pod.pdf",
        content=pdf,
        mime_type="application/pdf",
    )
    document = uploaded.body
    check(
        "a logistics document is stored privately with a checksum",
        uploaded.status == 201
        and document["sha256"] == hashlib.sha256(pdf).hexdigest()
        and document["version"] == 1,
        str(uploaded.body),
    )

    download = trader.call("GET", f"/api/v1/documents/{document['id']}/download")
    check(
        "the authorised download returns the exact bytes",
        download.status == 200
        and download.body == pdf.decode("utf-8", errors="replace"),
        f"{download.status} {str(download.body)[:40]}",
    )
    check(
        "download carries an attachment disposition and the digest",
        download.headers.get("content-disposition", "").startswith("attachment")
        and download.headers.get("x-document-sha256") == document["sha256"],
        str(download.headers),
    )

    cross_tenant = outsider.call("GET", f"/api/v1/documents/{document['id']}/download")
    check(
        "a different company cannot download the document",
        cross_tenant.status == 404,
        str(cross_tenant.status),
    )
    check(
        "a different company sees no orders, shipments or documents",
        sees_no_records(outsider, "/api/v1/sales-orders")
        and sees_no_records(outsider, "/api/v1/shipments")
        and sees_no_records(outsider, "/api/v1/documents"),
    )

    foreign_link = upload_document(
        trader,
        fields={
            "document_type": "OTHER",
            "linked_entity_type": "SALES_ORDER",
            "linked_entity_id": str(uuid.uuid4()),
            "title": "Should not be stored",
        },
        filename="orphan.pdf",
        content=pdf,
        mime_type="application/pdf",
    )
    check(
        "a document cannot be linked to a non-existent entity",
        foreign_link.status == 404,
        f"{foreign_link.status} {foreign_link.body}",
    )

    preview = trader.call(
        "GET",
        f"/api/v1/sales-orders/{order['id']}/documents/preview?kind=commercial_invoice",
    )
    header = preview.body.get("header", {}) if preview.status == 200 else {}
    check(
        "the draft invoice is labelled DRAFT with a legal notice",
        preview.status == 200
        and header.get("is_draft") is True
        and "not a legally issued" in header.get("legal_notice", ""),
        str(preview.body)[:300],
    )

    packing = trader.call(
        "GET",
        f"/api/v1/sales-orders/{order['id']}/documents/preview?kind=packing_list&shipment_id={shipment['id']}",
    )
    check(
        "the packing list shows the shipped quantity, not the ordered total",
        packing.status == 200 and packing.body["lines"][0]["shipment_quantity"] == "40.000",
        str(packing.body)[:300],
    )

    summary_response = trader.call("GET", "/api/v1/operations/summary")
    summary = summary_response.body if isinstance(summary_response.body, dict) else {}
    check(
        "operational summary counts the real rows",
        summary_response.status == 200
        and summary.get("orders_total", 0) >= 1
        and summary.get("documents_total", 0) >= 1
        and summary.get("delivered_shipments", 0) >= 2,
        f"{summary_response.status} {str(summary_response.body)[:250]}",
    )

    invoices = trader.call("GET", "/api/v1/invoices")
    payments = trader.call("GET", "/api/v1/payments")
    check(
        "no accounting revenue or payment endpoint exists",
        invoices.status == 404 and payments.status == 404,
        f"{invoices.status}/{payments.status}",
    )

    pages = [
        ("/orders", "Sales orders"),
        (f"/orders/{order['id']}", order["order_number"]),
        ("/purchase-orders", "Supplier purchase orders"),
        (f"/purchase-orders/{po['id']}", po["po_number"]),
        ("/shipments", "Shipments"),
        ("/shipments/new", "Plan a shipment"),
        (f"/shipments/{shipment['id']}", shipment["shipment_number"]),
        ("/documents", "Trade document register"),
    ]
    rendered = []
    for path, marker in pages:
        response = trader.page(path)
        rendered.append(response.status == 200 and marker in response.body)
    check(
        f"all {len(pages)} execution pages render from real data",
        all(rendered),
        str([page for page, ok in zip(pages, rendered, strict=True) if not ok]),
    )

    return finish()


def finish() -> int:
    print()
    print(f"{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        for label in FAILED:
            print(f"  failed: {label}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())









