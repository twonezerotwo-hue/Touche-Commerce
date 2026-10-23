"""Isolated HTTP acceptance verifier for Stages 5C, 5D and 5E.

The verifier never starts or points at the live Finance application. It creates a
temporary Finance base directory, initialises a synthetic SQLite ledger, creates a
temporary integration key, starts Finance on an isolated loopback port, starts
Commerce against the isolated test PostgreSQL database, and drives the real HTTP
APIs through a browser-like cookie jar.

Usage (from the Commerce repository):
    backend\\.venv\\Scripts\\python.exe backend\\scripts\\verify_finance_http.py
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any
from uuid import uuid4

_COMMERCE_ROOT = Path(__file__).resolve().parents[2]
_BACKEND_ROOT = _COMMERCE_ROOT / "backend"
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.core.config import Settings  # noqa: E402
from app.db.engine import Database  # noqa: E402
from app.security.passwords import PasswordService  # noqa: E402
from app.security.permissions import Role  # noqa: E402
from app.services import admin  # noqa: E402

COMMERCE_ROOT = _COMMERCE_ROOT
BACKEND_ROOT = _BACKEND_ROOT
FRONTEND_ROOT = COMMERCE_ROOT / "frontend"
FINANCE_ROOT = Path(r"C:\ai-excel")
FINANCE_SCRIPTS = FINANCE_ROOT / "scripts"
FINANCE_PYTHON = "py"
COMMERCE_API = "http://127.0.0.1:8000"
FRONTEND = "http://127.0.0.1:3000"
FINANCE_PORT = 8877
PASSWORD = "Stage5D-Isolated-Horse-9"  # noqa: S105 - temporary isolated test account only
ORIGIN = "http://localhost:3000"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(command: list[str], *, cwd: Path, env: dict[str, str], label: str) -> str:
    result = subprocess.run(  # noqa: S603 - fixed local tool invocations only
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"{label} failed ({result.returncode})\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result.stdout


def _finance_env(base: Path, **extra: str) -> dict[str, str]:
    return {
        **os.environ,
        "TOUCHE_BASE_DIR": str(base),
        "TOUCHE_MAIN_WORKBOOK": str(base / "workbook.xlsx"),
        "TOUCHE_BACKUP_WORKBOOK": str(base / "workbook_backup.xlsx"),
        "TOUCHE_INTEGRATION_KEYS_FILE": str(base / "integration_keys.json"),
        "TOUCHE_INTEGRATION_AUDIT_LOG": str(base / "integration_audit.jsonl"),
        "FINANS_UI_PORT": str(FINANCE_PORT),
        **extra,
    }


def _seed_finance(base: Path) -> None:
    seed = r"""
import sqlite3
from pathlib import Path

import config
import finans_cekirdegi as cekirdek
from openpyxl import Workbook

cekirdek.veritabanini_hazirla()
wb = Workbook()
wb.save(config.ana_excel_yolu())

def fis(con, fis_id, tarih, cari, lines, *, vade=None, para_birimi="TL"):
    con.execute(
        "INSERT INTO fisler(fis_id,belge_id,kayit_sira,faaliyet_key,tarih,vade,proje,cari,"
        "aciklama,para_birimi,kur_mikro,durum,olusturma_zamani) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (fis_id, fis_id, 1, "gursar_mimarlik", tarih, vade, "", cari, "",
         para_birimi, 1_000_000, "MUHASEBELESTI", "2026-01-01T00:00:00"),
    )
    for index, (code, debit, credit) in enumerate(lines, start=1):
        con.execute(
            "INSERT INTO fis_satirlari(fis_id,satir_no,hesap_kodu,borc_kurus,"
            "alacak_kurus,aciklama) VALUES(?,?,?,?,?,?)",
            (fis_id, index, code, debit, credit, ""),
        )

con = sqlite3.connect(cekirdek.DB_PATH)
try:
    fis(con, "F-AR-1", "2026-01-01", "Customer A", [("120", 100_000, 0)], vade="2026-01-31")
    fis(con, "F-AR-2", "2026-02-01", "Customer A", [("120", 0, 40_000)], vade="2026-02-28")
    fis(con, "F-AP-1", "2026-01-10", "Supplier B", [("320", 0, 50_000)], vade="2026-01-15")
    fis(con, "F-CASH", "2026-02-15", "Cash", [("100", 500_000, 0)])
    fis(con, "F-REV", "2026-02-20", "Customer A", [("600", 0, 100_000)])
    fis(con, "F-COST", "2026-02-21", "Supplier B", [("740", 10_000, 0)])
    fis(con, "F-EUR-1", "2026-02-22", "Customer EUR", [("120", 5_000, 0)], para_birimi="EUR")
    fis(
        con,
        "F-USD-AR-1",
        "2026-02-21",
        "Buyer Ltd",
        [("120", 25_000, 0)],
        vade="2026-03-31",
        para_birimi="USD",
    )
    con.commit()
finally:
    con.close()

print(f"ISOLATED_BASE={config.BASE_DIR}")
print(f"ISOLATED_DB={cekirdek.DB_PATH}")
print(f"ISOLATED_WORKBOOK={config.ana_excel_yolu()}")
"""
    _run(
        [FINANCE_PYTHON, "-3.12", "-c", seed],
        cwd=FINANCE_SCRIPTS,
        env=_finance_env(base),
        label="isolated Finance seed",
    )


def _create_key(base: Path) -> tuple[str, str]:
    stdout = _run(
        [
            FINANCE_PYTHON,
            "-3.12",
            "scripts/integration_keys.py",
            "--keys-file",
            str(base / "integration_keys.json"),
            "--json",
            "create",
            "--label",
            "stage5d-isolated-http",
            "--companies",
            "gursar_mimarlik",
        ],
        cwd=FINANCE_ROOT,
        env=_finance_env(base, TOUCHE_INTEGRATION_ENABLED="false"),
        label="temporary Finance key creation",
    )
    start = stdout.find("{")
    if start < 0:
        raise RuntimeError(f"key creation did not emit JSON: {stdout}")
    payload = json.loads(stdout[start:])
    return str(payload["key_id"]), str(payload["secret"])


def _seed_commerce(settings: Settings) -> dict[str, Any]:
    migration_dsn = settings.test_migration_dsn
    if migration_dsn is None:
        raise RuntimeError("The isolated Commerce test database is not configured.")
    database = Database(settings, dsn_override=migration_dsn)
    password_hash = PasswordService(settings).hash(PASSWORD)
    suffix = uuid4().hex[:8]
    company_a_name = f"Stage5D Commerce {suffix}"
    company_b_name = f"Stage5D Other {suffix}"
    email = f"stage5d-{suffix}@touche.example"
    trader_email = f"stage5d-trader-{suffix}@touche.example"
    reviewer_email = f"stage5d-reviewer-{suffix}@touche.example"
    try:
        with database.transaction() as session:
            company_a = admin.create_company(
                session, name=company_a_name, country="TR", default_currency="TRY"
            )
            company_b = admin.create_company(
                session, name=company_b_name, country="TR", default_currency="TRY"
            )
            user = admin.create_user(
                session,
                email=email,
                display_name="Stage 5D Isolated Admin",
                password_hash=password_hash,
            )
            trader = admin.create_user(
                session,
                email=trader_email,
                display_name="Stage 5D Isolated Trader",
                password_hash=password_hash,
            )
            reviewer = admin.create_user(
                session,
                email=reviewer_email,
                display_name="Stage 5D Isolated Reviewer",
                password_hash=password_hash,
            )
            admin.grant_membership(
                session, user_id=user.id, company_id=company_a.id, role=Role.ADMIN
            )
            admin.grant_membership(
                session, user_id=user.id, company_id=company_b.id, role=Role.VIEWER
            )
            admin.grant_membership(
                session, user_id=trader.id, company_id=company_a.id, role=Role.TRADER
            )
            admin.grant_membership(
                session, user_id=reviewer.id, company_id=company_a.id, role=Role.APPROVER
            )
            return {
                "company_a": str(company_a.id),
                "company_b": str(company_b.id),
                "company_a_name": company_a_name,
                "company_b_name": company_b_name,
                "user_id": str(user.id),
                "email": email,
                "trader_email": trader_email,
                "reviewer_email": reviewer_email,
            }
    finally:
        database.dispose()


class Client:
    def __init__(self) -> None:
        self.jar = CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def request(
        self,
        method: str,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, Any], str]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request_headers = {
            "Accept": "application/json",
            "User-Agent": "stage5d-isolated-verifier",
            **dict(headers or {}),
        }
        if body is not None:
            request_headers["Content-Type"] = "application/json"
        request = urllib.request.Request(  # noqa: S310 - fixed loopback URLs only
            url, data=body, headers=request_headers, method=method
        )
        try:
            with self.opener.open(request, timeout=30) as response:
                text = response.read().decode("utf-8", "replace")
                return int(response.status), self._json(text), text
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", "replace")
            return int(exc.code), self._json(text), text

    def fetch(
        self, url: str, *, headers: dict[str, str] | None = None
    ) -> tuple[int, dict[str, str], str]:
        """GET returning the lower-cased response headers (used for the CSV export)."""

        request = urllib.request.Request(  # noqa: S310 - fixed loopback URLs only
            url,
            headers={"User-Agent": "stage5e-isolated-verifier", **dict(headers or {})},
            method="GET",
        )
        try:
            with self.opener.open(request, timeout=30) as response:
                return (
                    int(response.status),
                    {key.lower(): value for key, value in response.headers.items()},
                    response.read().decode("utf-8", "replace"),
                )
        except urllib.error.HTTPError as exc:
            return (
                int(exc.code),
                {key.lower(): value for key, value in exc.headers.items()},
                exc.read().decode("utf-8", "replace"),
            )

    @staticmethod
    def _json(text: str) -> dict[str, Any]:
        try:
            payload = json.loads(text)
            return payload if isinstance(payload, dict) else {}
        except json.JSONDecodeError:
            return {}


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _login_client(email: str, company_id: str) -> tuple[Client, str]:
    client = Client()
    status, body, text = client.request(
        "POST",
        f"{COMMERCE_API}/api/v1/auth/login",
        payload={"email": email, "password": PASSWORD},
        headers={"Origin": ORIGIN},
    )
    if status != 200:
        raise AssertionError(f"login failed for {email}: {status} {text}")
    csrf = str(body["session"]["csrf_token"])
    if body["session"]["company"] is None:
        status, body, text = client.request(
            "POST",
            f"{COMMERCE_API}/api/v1/session/company",
            payload={"company_id": company_id},
            headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
        )
        if status != 200:
            raise AssertionError(f"company switch failed for {email}: {status} {text}")
        csrf = str(body["session"]["csrf_token"])
    return client, csrf


def _stage5d_acceptance(world: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create and reconcile a real Commerce order through HTTP.

    Returns the Stage 5D summary and the live clients/records Stage 5E re-uses.
    """

    texts: list[str] = []
    trader, trader_csrf = _login_client(world["trader_email"], world["company_a"])
    reviewer, reviewer_csrf = _login_client(world["reviewer_email"], world["company_a"])
    future = (date.today() + timedelta(days=30)).isoformat()

    def post(
        client: Client,
        csrf: str,
        path: str,
        payload: dict[str, Any] | None,
        *,
        expected: int | tuple[int, ...] = (200, 201, 204),
        if_match: str | None = None,
    ) -> dict[str, Any]:
        headers = {"Origin": ORIGIN, "X-CSRF-Token": csrf, "Idempotency-Key": uuid4().hex}
        if if_match:
            headers["If-Match"] = if_match
        status, body, text = client.request(
            "POST", f"{COMMERCE_API}{path}", payload=payload, headers=headers
        )
        texts.append(text)
        allowed = (expected,) if isinstance(expected, int) else expected
        if status not in allowed:
            raise AssertionError(f"POST {path}: expected {allowed}, got {status}: {text}")
        return body

    def get(client: Client, path: str, *, expected: int = 200) -> dict[str, Any]:
        status, body, text = client.request("GET", f"{COMMERCE_API}{path}")
        texts.append(text)
        if status != expected:
            raise AssertionError(f"GET {path}: expected {expected}, got {status}: {text}")
        return body

    supplier = post(
        trader,
        trader_csrf,
        "/api/v1/counterparties",
        {"name": "Stage 5D Supplier", "type": "supplier", "country": "TR"},
        expected=201,
    )
    buyer = post(
        trader,
        trader_csrf,
        "/api/v1/counterparties",
        {"name": "Buyer Ltd", "type": "buyer", "country": "TR"},
        expected=201,
    )
    product = post(
        trader,
        trader_csrf,
        "/api/v1/products",
        {
            "sku": "S5D-ALM",
            "name": "Stage 5D Almond",
            "unit": "kg",
            "currency": "USD",
            "unit_price": "2.0000",
        },
        expected=201,
    )
    deal = post(
        trader,
        trader_csrf,
        "/api/v1/deals",
        {
            "title": "Stage 5D reconciliation order",
            "counterparty_id": buyer["id"],
            "currency": "USD",
            "items": [
                {
                    "product_id": product["id"],
                    "quantity": "100.000",
                    "unit_price": "2.0000",
                }
            ],
        },
        expected=201,
    )
    deal = post(
        trader,
        trader_csrf,
        f"/api/v1/deals/{deal['id']}/transitions",
        {"to": "OPEN"},
        if_match=f'"v{deal["version"]}"',
    )

    rfqs = post(
        trader,
        trader_csrf,
        "/api/v1/rfqs",
        {
            "deal_id": deal["id"],
            "supplier_ids": [supplier["id"]],
            "requested_currency": "USD",
            "delivery_location": "Rotterdam, NL",
            "response_due_date": future,
            "items": [
                {
                    "product_id": product["id"],
                    "description": "Almond kernels, 25 kg bags",
                    "quantity": "100.000",
                    "unit": "kg",
                }
            ],
        },
        expected=201,
    )
    rfq = rfqs["items"][0]
    post(
        trader,
        trader_csrf,
        f"/api/v1/rfqs/{rfq['id']}/transitions",
        {"to": "PREPARED"},
    )
    post(
        trader,
        trader_csrf,
        f"/api/v1/rfqs/{rfq['id']}/transitions",
        {"to": "SENT", "channel": "email", "evidence": "message-id:<stage5d-rfq>"},
    )
    supplier_quote = post(
        trader,
        trader_csrf,
        f"/api/v1/rfqs/{rfq['id']}/quotes",
        {
            "currency": "USD",
            "incoterm": "CIF",
            "named_delivery_place": "Rotterdam, NL",
            "payment_terms": "30 days net",
            "lead_time_days": 21,
            "valid_until": future,
            "source_reference": "email: stage5d supplier quote",
            "items": [
                {
                    "product_id": product["id"],
                    "quantity": "100.000",
                    "unit_price": "1.6000",
                }
            ],
        },
        expected=201,
    )
    scenario = post(
        trader,
        trader_csrf,
        "/api/v1/pricing-scenarios",
        {
            "supplier_quote_id": supplier_quote["id"],
            "target_currency": "USD",
            "margin_pct": "20",
            "markup_pct": "0",
            "components": [
                {
                    "cost_type": "FREIGHT",
                    "amount": "40.00",
                    "currency": "USD",
                    "basis": "ORDER",
                    "source_reference": "stage5d-freight-quote",
                    "verification_status": "VERIFIED",
                }
            ],
        },
        expected=201,
    )
    sales_quote = post(
        trader,
        trader_csrf,
        "/api/v1/sales-quotes",
        {
            "scenario_id": scenario["id"],
            "customer_id": buyer["id"],
            "valid_until": future,
            "incoterm": "CIF",
            "named_delivery_place": "Rotterdam, NL",
            "payment_terms": "30 days net",
        },
        expected=201,
    )
    submitted_quote = post(
        trader,
        trader_csrf,
        f"/api/v1/sales-quotes/{sales_quote['id']}/submit",
        {},
        if_match=f'"v{sales_quote["version"]}"',
    )
    approved_quote = post(
        reviewer,
        reviewer_csrf,
        f"/api/v1/sales-quotes/{sales_quote['id']}/approve",
        {},
        if_match=f'"v{submitted_quote["version"]}"',
    )
    acceptance = post(
        trader,
        trader_csrf,
        f"/api/v1/deals/{deal['id']}/customer-acceptance",
        {
            "channel": "SIGNED_QUOTE",
            "accepted_at": datetime.now(tz=UTC).isoformat(),
            "accepted_by_name": "Dana Buyer",
            "evidence_reference": "stage5d signed order",
        },
        expected=201,
    )
    order = post(
        trader,
        trader_csrf,
        f"/api/v1/deals/{deal['id']}/sales-order",
        {
            "sales_quote_id": approved_quote["id"],
            "acceptance_evidence_id": acceptance["id"],
            "fulfilment_model": "PURCHASE_RESALE",
        },
        expected=201,
    )
    if Decimal(str(order["order_total"])) != Decimal("250.00"):
        raise AssertionError(f"unexpected accepted order total: {order['order_total']}")

    purchase_order = post(
        trader,
        trader_csrf,
        "/api/v1/purchase-orders",
        {
            "sales_order_id": order["id"],
            "supplier_id": supplier["id"],
            "supplier_quote_id": supplier_quote["id"],
            "incoterm": "CIF",
            "named_delivery_place": "Rotterdam, NL",
            "payment_terms": "30 days net",
            "expected_dispatch_date": future,
            "items": [
                {
                    "product_id": product["id"],
                    "quantity": "100.000",
                    "unit": "kg",
                    "unit_cost": "1.6000",
                }
            ],
        },
        expected=201,
    )
    post(
        reviewer,
        reviewer_csrf,
        f"/api/v1/purchase-orders/{purchase_order['id']}/transitions",
        {"target": "APPROVED"},
        if_match=f'"v{purchase_order["version"]}"',
    )
    shipment = post(
        trader,
        trader_csrf,
        "/api/v1/shipments",
        {
            "sales_order_id": order["id"],
            "transport_mode": "SEA",
            "origin": "Jebel Ali, AE",
            "destination": "Rotterdam, NL",
            "carrier": "Stage 5D Carrier",
            "forwarder": "Stage 5D Forwarder",
            "planned_dispatch_at": (datetime.now(tz=UTC) + timedelta(days=3)).isoformat(),
            "estimated_arrival_at": (datetime.now(tz=UTC) + timedelta(days=21)).isoformat(),
            "items": [
                {
                    "sales_order_item_id": order["items"][0]["id"],
                    "quantity": "10.000",
                }
            ],
        },
        expected=201,
    )
    post(
        trader,
        trader_csrf,
        f"/api/v1/shipments/{shipment['id']}/costs",
        {
            "cost_type": "FREIGHT",
            "stage": "INCURRED",
            "amount": "20.00",
            "currency": "USD",
            "reference": "stage5d-freight-invoice",
        },
        expected=(200, 201),
    )
    run = post(
        trader,
        trader_csrf,
        "/api/v1/finance/reconciliation/runs",
        {
            "sales_order_id": order["id"],
            "currency": "USD",
            "as_of": date.today().isoformat(),
        },
        expected=201,
    )
    if run["status"] != "UNMATCHED":
        raise AssertionError(f"new complete run was not UNMATCHED: {run['status']}")
    source = next(
        (
            item
            for item in run["source_references"]
            if item["source_type"] == "AGING_RECEIVABLE"
            and item["source_reference"] == "F-USD-AR-1"
        ),
        None,
    )
    if source is None:
        raise AssertionError("isolated Finance USD AR source id was not captured")
    if Decimal(str(source["observed_amount"])) != Decimal(str(order["order_total"])):
        raise AssertionError("Finance source amount does not match the accepted order total")

    evidence = post(
        trader,
        trader_csrf,
        "/api/v1/finance/evidence-links",
        {
            "run_id": run["id"],
            "source_entity_type": "SALES_ORDER",
            "source_entity_id": order["id"],
            "finance_source_reference_id": source["id"],
            "notes": "Signed order and Finance open item reviewed together.",
        },
        expected=201,
        if_match=f'"v{run["version"]}"',
    )
    if evidence["status"] != "MATCHED_EVIDENCE":
        raise AssertionError(f"exact evidence did not reach MATCHED_EVIDENCE: {evidence['status']}")

    unauthorized = post(
        trader,
        trader_csrf,
        "/api/v1/finance/reviews",
        {"run_id": evidence["id"], "decision": "CONFIRM", "notes": "Trader must not review."},
        expected=403,
        if_match=f'"v{evidence["version"]}"',
    )
    if unauthorized["error"]["code"] != "FORBIDDEN":
        raise AssertionError("unauthorized reviewer did not receive FORBIDDEN")

    verified = post(
        reviewer,
        reviewer_csrf,
        "/api/v1/finance/reviews",
        {
            "run_id": evidence["id"],
            "decision": "CONFIRM",
            "notes": "Source id, amount and currency checked.",
        },
        expected=201,
        if_match=f'"v{evidence["version"]}"',
    )
    if verified["status"] != "VERIFIED":
        raise AssertionError(f"reviewer confirmation did not verify: {verified['status']}")

    unmatched_run = post(
        trader,
        trader_csrf,
        "/api/v1/finance/reconciliation/runs",
        {
            "sales_order_id": order["id"],
            "currency": "USD",
            "as_of": date.today().isoformat(),
        },
        expected=201,
    )
    unmatched_review = post(
        reviewer,
        reviewer_csrf,
        "/api/v1/finance/reviews",
        {
            "run_id": unmatched_run["id"],
            "decision": "CONFIRM",
            "notes": "No evidence exists for this run.",
        },
        expected=409,
        if_match=f'"v{unmatched_run["version"]}"',
    )
    if unmatched_review["error"]["code"] != "RECONCILIATION_NOT_VERIFIABLE":
        raise AssertionError("unlinked run was not refused verification")
    if unmatched_run["status"] == "VERIFIED":
        raise AssertionError("unlinked run was incorrectly verified")

    get(trader, f"/api/v1/finance/reconciliation/runs/{verified['id']}")
    get(trader, "/api/v1/finance/reconciliation?currency=USD")
    get(trader, f"/api/v1/finance/orders/{order['id']}")
    get(trader, f"/api/v1/finance/discrepancies?run_id={unmatched_run['id']}")

    frontend_checks = {
        f"{FRONTEND}/finance/reconciliation?currency=USD": "Reconciliation",
        f"{FRONTEND}/finance/reconciliation/{verified['id']}": verified["order_number"],
        f"{FRONTEND}/finance/discrepancies": "Discrepancies",
        f"{FRONTEND}/finance/orders/{order['id']}": order["order_number"],
    }
    for url, marker in frontend_checks.items():
        status, _body, text = trader.request("GET", url)
        texts.append(text)
        if status != 200 or marker not in text:
            raise AssertionError(f"frontend did not render {url}: {status}")

    admin, admin_csrf = _login_client(world["email"], world["company_a"])
    status, _body, text = admin.request(
        "POST",
        f"{COMMERCE_API}/api/v1/session/company",
        payload={"company_id": world["company_b"]},
        headers={"Origin": ORIGIN, "X-CSRF-Token": admin_csrf},
    )
    texts.append(text)
    if status != 200:
        raise AssertionError(f"cross-tenant switch failed: {status} {text}")
    get(admin, f"/api/v1/finance/reconciliation/runs/{verified['id']}", expected=404)
    other_runs = get(admin, "/api/v1/finance/reconciliation?currency=USD")
    if other_runs["items"]:
        raise AssertionError("cross-tenant reconciliation runs were visible")

    post_status, _post_body, post_text = trader.request(
        "POST",
        f"{COMMERCE_API}/api/v1/finance/summary?currency=USD",
        headers={"Origin": ORIGIN},
    )
    texts.append(post_text)
    if post_status != 405:
        raise AssertionError(f"Finance ledger write route was not rejected: {post_status}")

    joined = "\n".join(texts)
    if "s" * 43 in joined:
        raise AssertionError("Finance credentials leaked into Stage 5D responses")

    summary = {
        "order_number": order["order_number"],
        "order_total": order["order_total"],
        "run_status": verified["status"],
        "evidence_status": verified["evidence_links"][0]["verification_status"],
        "review_decision": verified["reviews"][-1]["decision"],
        "unauthorized_review": unauthorized["error"]["code"],
        "unlinked_run_cannot_verify": True,
        "finance_source_id": source["source_reference"],
        "finance_source_amount": source["observed_amount"],
        "frontend_routes": [
            "reconciliation",
            "reconciliation_run",
            "discrepancies",
            "order_finance",
        ],
        "cross_tenant_isolated": True,
        "write_route_rejected": post_status,
        "credentials_in_responses": False,
    }
    context = {
        "trader": trader,
        "trader_csrf": trader_csrf,
        "reviewer": reviewer,
        "reviewer_csrf": reviewer_csrf,
        "order": order,
        "texts": texts,
    }
    return summary, context


def _stage5e_acceptance(world: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Drive the Stage 5E intelligence API, CSV export and screens with the real order.

    The order is the Stage 5D one: 100 kg sold for 250.00 USD against a 160.00 USD
    approved purchase order and a 40.00 USD freight estimate, with only 10 kg
    shipped and 20.00 USD of freight actually incurred. The expected figures below
    follow from those inputs, not from the implementation under test.
    """

    trader: Client = context["trader"]
    reviewer: Client = context["reviewer"]
    trader_csrf: str = context["trader_csrf"]
    reviewer_csrf: str = context["reviewer_csrf"]
    order: dict[str, Any] = context["order"]
    texts: list[str] = context["texts"]
    order_id = str(order["id"])
    order_number = str(order["order_number"])
    intelligence = f"{COMMERCE_API}/api/v1/finance/intelligence"
    pages = f"{FRONTEND}/finance/intelligence"

    def api_get(
        client: Client, path: str, *, expected: int | tuple[int, ...] = 200
    ) -> dict[str, Any]:
        status, body, text = client.request("GET", f"{intelligence}{path}")
        texts.append(text)
        allowed = (expected,) if isinstance(expected, int) else expected
        _check(status in allowed, f"GET intelligence{path}: expected {allowed}, got {status}")
        return body

    def api_post(
        client: Client,
        csrf: str,
        url: str,
        payload: dict[str, Any],
        *,
        expected: int | tuple[int, ...],
        if_match: str | None = None,
    ) -> dict[str, Any]:
        headers = {"Origin": ORIGIN, "X-CSRF-Token": csrf, "Idempotency-Key": uuid4().hex}
        if if_match:
            headers["If-Match"] = if_match
        status, body, text = client.request("POST", url, payload=payload, headers=headers)
        texts.append(text)
        allowed = (expected,) if isinstance(expected, int) else expected
        _check(status in allowed, f"POST {url}: expected {allowed}, got {status}: {text}")
        return body

    def page(client: Client, path: str, *markers: str) -> str:
        status, _body, text = client.request("GET", f"{pages}{path}")
        texts.append(text)
        _check(status == 200, f"frontend {pages}{path} returned {status}")
        for marker in markers:
            _check(marker in text, f"frontend {pages}{path} did not render {marker!r}")
        return text

    def money_of(metric: dict[str, Any], currency: str = "USD") -> Decimal | None:
        return next(
            (
                Decimal(str(item["amount"]))
                for item in metric["money"]
                if item["currency"] == currency
            ),
            None,
        )

    # --- summary: real figures, per currency, with the read-only guarantees ---------
    summary = api_get(trader, "/summary")
    _check(str(summary["calculation_version"]).startswith("stage5e-"), "unexpected version")
    _check(
        summary["read_only"] is True
        and summary["accounting_writes_enabled"] is False
        and summary["statutory_statements"] is False,
        "summary lost a read-only guarantee",
    )
    _check(
        summary["order_count"] == 1 and summary["active_order_count"] == 1,
        f"unexpected order counts: {summary['order_count']}/{summary['active_order_count']}",
    )
    metrics = {item["key"]: item for item in summary["metrics"]}
    expected_keys = {
        "accepted_sales_order_value",
        "purchase_commitments",
        "estimated_gross_profit",
        "estimated_gross_margin",
        "recorded_operational_costs",
        "reconciliation_coverage",
        "open_discrepancies",
        "committed_gross_profit",
    }
    _check(
        expected_keys <= set(metrics), f"missing metrics: {sorted(expected_keys - set(metrics))}"
    )
    expected_money = {
        "accepted_sales_order_value": "250.00",
        "purchase_commitments": "160.00",
        "estimated_gross_profit": "50.00",
        "recorded_operational_costs": "20.00",
    }
    for key, expected in expected_money.items():
        _check(
            money_of(metrics[key]) == Decimal(expected),
            f"metric {key}: expected {expected} USD, got {metrics[key]['money']}",
        )
    # The metric's classification names its kind and stays COMMITTED; what matters is that
    # no figure is reported while the only order is part-shipped (the screens then say
    # "Not available" and label it UNAVAILABLE).
    committed_metric = metrics["committed_gross_profit"]
    _check(
        not committed_metric["available"]
        and not committed_metric["money"]
        and not committed_metric["percentages"],
        f"committed profit was reported while the order is part-shipped: {committed_metric}",
    )
    currencies = {item["currency"] for metric in summary["metrics"] for item in metric["money"]}
    _check(currencies == {"USD"}, f"metrics mixed or invented currencies: {currencies}")

    # --- order list: every figure follows from the known inputs ---------------------
    listing = api_get(trader, "/orders?limit=1&offset=0")
    _check(
        listing["total"] == 1 and len(listing["items"]) == 1, "order list did not hold one order"
    )
    row = listing["items"][0]
    _check(
        row["sales_order_id"] == order_id and row["order_number"] == order_number,
        "order list returned a different order",
    )
    expected_figures = {
        "sales_value": "250.00",
        "estimated_landed_cost": "200.00",
        "estimated_gross_profit": "50.00",
        "estimated_gross_margin_pct": "20.00",
        "estimated_markup_pct": "25.00",
        "committed_purchase_cost": "160.00",
        "documented_operational_cost": "20.00",
    }
    for key, expected in expected_figures.items():
        _check(
            row[key] is not None and Decimal(str(row[key])) == Decimal(expected),
            f"order {key}: expected {expected}, got {row[key]}",
        )
    _check(row["currency"] == "USD", "order currency changed")
    _check(row["partial_fulfilment"] is True, "partial fulfilment was not flagged")
    _check(
        row["committed_gross_profit"] is None, "committed profit claimed on a part-shipped order"
    )
    _check("PARTIAL_FULFILMENT" in row["missing_components"], "partial fulfilment not listed")
    _check(row["committed_status"] == "PARTIAL", f"committed status was {row['committed_status']}")
    _check("actual_profit" not in row, "an actual_profit field exists")
    _check(
        row["classifications"]["actual_profit"] == "UNAVAILABLE", "actual profit not unavailable"
    )
    _check(row["run_count"] == 2, f"expected the 2 Stage 5D runs, got {row['run_count']}")
    _check(row["open_discrepancy_count"] >= 1, "no open discrepancy reached the order row")

    # --- filters and validation ------------------------------------------------------
    _check(
        api_get(trader, "/summary?currency=EUR")["order_count"] == 0, "EUR filter kept a USD order"
    )
    _check(api_get(trader, "/orders?currency=USD")["total"] == 1, "USD filter lost the order")
    _check(
        api_get(trader, "/orders?fulfilment_model=PURCHASE_RESALE")["total"] == 1,
        "fulfilment-model filter lost the order",
    )
    _check(
        api_get(trader, "/orders?fulfilment_model=BROKERAGE")["total"] == 0,
        "fulfilment-model filter kept the wrong model",
    )
    api_get(trader, "/summary?from=2999-12-31&to=2000-01-01", expected=(400, 422))

    # --- cost variance and coverage --------------------------------------------------
    variance = api_get(trader, "/cost-variance")
    _check(
        variance["total"] == 0 and variance["excluded_order_count"] == 1,
        f"a part-shipped order produced a cost variance: {variance['total']}",
    )
    coverage = api_get(trader, "/coverage")
    _check(coverage["order_count"] == 1, "coverage order count was wrong")
    _check(sum(item["count"] for item in coverage["estimate"]) == 1, "estimate coverage mismatch")

    # --- order drill-down ------------------------------------------------------------
    detail = api_get(trader, f"/orders/{order_id}")
    _check(
        detail["read_only"] is True
        and detail["accounting_writes_enabled"] is False
        and detail["statutory_statements"] is False,
        "detail lost a read-only guarantee",
    )
    _check(detail["order"]["sales_order_id"] == order_id, "detail returned a different order")
    _check(detail["quote"]["currency"] == "USD" and detail["quote"]["lines"], "quote missing")
    po_rows = detail["purchase_orders"]
    _check(
        len(po_rows) == 1
        and Decimal(str(po_rows[0]["total_cost"])) == Decimal("160.00")
        and po_rows[0]["classification"] == "COMMITTED",
        f"purchase order detail wrong: {po_rows}",
    )
    shipment_costs = [cost for shipment in detail["shipments"] for cost in shipment["costs"]]
    _check(
        any(
            cost["stage"] == "INCURRED"
            and Decimal(str(cost["amount"])) == Decimal("20.00")
            and cost["classification"] == "DOCUMENTED"
            for cost in shipment_costs
        ),
        f"incurred freight missing from detail: {shipment_costs}",
    )
    _check(
        any(
            line["cost_type"] == "FREIGHT"
            and Decimal(str(line["converted_amount"])) == Decimal("40.00")
            for line in detail["cost_lines"]
        ),
        "estimated freight line missing from the cost lines",
    )
    _check(len(detail["runs"]) == 2, f"expected 2 runs in the timeline, got {len(detail['runs'])}")
    verified_evidence = [
        item
        for item in detail["evidence"]
        if item["finance_source_reference"] == "F-USD-AR-1"
        and Decimal(str(item["amount"])) == Decimal("250.00")
        and item["verification_status"] == "VERIFIED"
    ]
    _check(len(verified_evidence) == 1, "verified Finance evidence missing from the drill-down")
    _check(bool(detail["limitations"]) and bool(detail["checks"]), "limitations or checks empty")
    _check(
        all(item["sales_order_id"] == order_id for item in detail["discrepancies"]),
        "detail listed another order's discrepancies",
    )
    api_get(trader, f"/orders/{uuid4()}", expected=404)

    # --- exceptions: enrichment, permission and resolution ---------------------------
    open_before = api_get(trader, "/exceptions?status=OPEN&limit=50")
    _check(open_before["total"] >= 1, "no open financial exception for the order")
    _check(
        all(
            item["sales_order_id"] == order_id
            and item["order_number"] == order_number
            and item["currency"] == "USD"
            for item in open_before["items"]
        ),
        "exceptions were not enriched with the order",
    )
    target = open_before["items"][0]
    resolve_url = f"{COMMERCE_API}/api/v1/finance/discrepancies/{target['id']}/resolve"
    denied = api_post(
        trader,
        trader_csrf,
        resolve_url,
        {"notes": "A trader must not resolve this."},
        expected=403,
        if_match=f'"v{target["version"]}"',
    )
    _check(denied["error"]["code"] == "FORBIDDEN", "trader resolution was not FORBIDDEN")
    api_post(
        reviewer,
        reviewer_csrf,
        resolve_url,
        {"notes": "Reviewed against the isolated Finance receivable."},
        expected=(200, 201),
        if_match=f'"v{target["version"]}"',
    )
    open_after = api_get(trader, "/exceptions?status=OPEN&limit=50")
    _check(
        open_after["total"] == open_before["total"] - 1,
        f"resolving did not shrink the open queue: {open_before['total']} -> {open_after['total']}",
    )
    resolved = api_get(trader, "/exceptions?status=RESOLVED&limit=50")
    _check(
        any(
            item["id"] == target["id"] and bool(item["resolution_notes"])
            for item in resolved["items"]
        ),
        "the resolved exception is missing from the RESOLVED list",
    )
    all_statuses = api_get(trader, "/exceptions?status=&limit=50")
    _check(all_statuses["total"] >= open_after["total"] + 1, "the empty status filter hid items")

    # --- CSV export: API and through the same-origin proxy ---------------------------
    csv_status, csv_headers, csv_text = trader.fetch(
        f"{intelligence}/export?currency=USD", headers={"Accept": "text/csv"}
    )
    texts.append(csv_text)
    _check(csv_status == 200, f"export returned {csv_status}")
    _check(csv_headers.get("content-type", "").startswith("text/csv"), "export is not text/csv")
    _check(
        "attachment;" in csv_headers.get("content-disposition", ""), "export is not an attachment"
    )
    _check(csv_headers.get("x-content-type-options") == "nosniff", "export lost nosniff")
    csv_rows = list(csv.DictReader(io.StringIO(csv_text, newline="")))
    _check(len(csv_rows) == 1, f"export held {len(csv_rows)} rows for one order")
    export_row = csv_rows[0]
    _check(
        export_row["sales_order_id"] == order_id and export_row["order_number"] == order_number,
        "export row is for a different order",
    )
    _check(export_row["estimated_gross_profit"] == "50.00", "export profit did not match the API")
    _check(export_row["committed_gross_profit"] == "", "export claimed a committed profit")
    _check("actual_profit" not in export_row, "export has an actual_profit column")
    _check("not accounting profit" in export_row["analysis_notice"], "export lost its notice")
    eur_text = trader.fetch(f"{intelligence}/export?currency=EUR")[2]
    eur_rows = list(csv.DictReader(io.StringIO(eur_text, newline="")))
    _check(not eur_rows, "EUR export contained the USD order")
    proxy_status, proxy_headers, proxy_text = trader.fetch(
        f"{FRONTEND}/api/v1/finance/intelligence/export?currency=USD"
    )
    texts.append(proxy_text)
    _check(proxy_status == 200 and order_number in proxy_text, "export via the proxy failed")
    _check(
        'filename="' in proxy_headers.get("content-disposition", ""),
        "the proxy dropped the export file name",
    )
    _check(
        proxy_headers.get("x-content-type-options") == "nosniff",
        "the proxy dropped the export nosniff header",
    )

    # --- screens rendered by Next.js from the live API -------------------------------
    notice = "not accounting profit"
    page(
        trader,
        "?currency=USD",
        "Financial intelligence",
        "Operational analysis",
        "Monthly commitments",
        "Export CSV",
        notice,
        "250.00",
    )
    page(trader, "?currency=EUR", "Financial intelligence", "No monthly commitments")
    page(
        trader,
        "?currency=bad!!&customer_id=nope&from=31%2F12%2F2026",
        "Financial intelligence",
        "250.00",
    )
    page(
        trader,
        "/orders",
        "Order profitability",
        order_number,
        f"/finance/intelligence/orders/{order_id}",
        "Cost variance",
    )
    page(
        trader, "/orders?view=variance", "Variance needs two complete bases", "No comparable orders"
    )
    page(
        trader,
        f"/orders/{order_id}",
        order_number,
        "Actual profit",
        "Not available",
        "Completion checks",
        "Limitations",
        "Reconciliation timeline",
        "F-USD-AR-1",
    )
    page(trader, f"/orders/{uuid4()}", "Could not load the order analysis")
    trader_exceptions = page(
        trader,
        "/exceptions",
        "Financial exceptions",
        order_number,
        "Read-only: resolving needs finance.reconcile.",
    )
    _check("You can resolve items" not in trader_exceptions, "trader saw the reviewer hint")
    page(
        reviewer,
        "/exceptions",
        "Financial exceptions",
        order_number,
        "You can resolve items with finance.reconcile.",
        "Resolve",
    )
    page(trader, "/exceptions?status=ALL", "Financial exceptions", "RESOLVED")

    # --- tenant isolation and read-only -----------------------------------------------
    outsider, outsider_csrf = _login_client(world["email"], world["company_a"])
    switched_status, _switched_body, switched_text = outsider.request(
        "POST",
        f"{COMMERCE_API}/api/v1/session/company",
        payload={"company_id": world["company_b"]},
        headers={"Origin": ORIGIN, "X-CSRF-Token": outsider_csrf},
    )
    texts.append(switched_text)
    _check(switched_status == 200, f"cross-tenant switch failed: {switched_status}")
    _check(api_get(outsider, "/summary")["order_count"] == 0, "another company saw the order count")
    _check(api_get(outsider, "/orders")["total"] == 0, "another company listed the order")
    api_get(outsider, f"/orders/{order_id}", expected=404)
    _check(api_get(outsider, "/exceptions?status=")["total"] == 0, "another company saw exceptions")
    outsider_csv = outsider.fetch(f"{intelligence}/export")[2]
    _check(order_number not in outsider_csv, "another company's export contained the order")
    outsider_page = page(outsider, f"/orders/{order_id}", "Could not load the order analysis")
    _check(order_number not in outsider_page, "another company's screen showed the order")
    _check(order_number not in page(outsider, "/orders"), "another company's list showed the order")

    write_status, _write_body, write_text = trader.request(
        "POST", f"{intelligence}/summary", headers={"Origin": ORIGIN}
    )
    texts.append(write_text)
    _check(write_status == 405, f"intelligence write-shaped route was not rejected: {write_status}")

    return {
        "order_number": order_number,
        "sales_value": row["sales_value"],
        "estimated_landed_cost": row["estimated_landed_cost"],
        "estimated_gross_profit": row["estimated_gross_profit"],
        "estimated_gross_margin_pct": row["estimated_gross_margin_pct"],
        "committed_purchase_cost": row["committed_purchase_cost"],
        "documented_operational_cost": row["documented_operational_cost"],
        "committed_profit_withheld_while_partly_shipped": True,
        "actual_profit_available": False,
        "cost_variance_orders": variance["total"],
        "cost_variance_excluded": variance["excluded_order_count"],
        "open_exceptions_before_resolution": open_before["total"],
        "open_exceptions_after_resolution": open_after["total"],
        "trader_resolution": denied["error"]["code"],
        "export_rows": len(csv_rows),
        "export_via_proxy_keeps_filename_and_nosniff": True,
        "api_routes": [
            "summary",
            "orders",
            "orders/{id}",
            "cost-variance",
            "coverage",
            "exceptions",
            "export",
        ],
        "frontend_routes": ["dashboard", "orders", "variance", "order_detail", "exceptions"],
        "cross_tenant_isolated": True,
        "write_route_rejected": write_status,
    }


def _wait(url: str, *, timeout: float, label: str) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(  # noqa: S310 - loopback wait probe
                url, timeout=2
            ) as response:
                if response.status < 500:
                    return
        except Exception:
            time.sleep(0.4)
    raise RuntimeError(f"Timed out waiting for {label} at {url}")


def _assert_port_free(port: int) -> None:
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", port)) == 0:
            raise RuntimeError(f"Refusing to start: port {port} is already in use.")


def _finance_paths(base: Path) -> dict[str, str]:
    code = (
        "import json, config, finans_cekirdegi as c;"
        "print(json.dumps({'base': str(config.BASE_DIR), 'db': str(c.DB_PATH),"
        " 'workbook': str(config.ana_excel_yolu()), 'logs': str(config.LOGLAR)}))"
    )
    stdout = _run(
        [FINANCE_PYTHON, "-3.12", "-c", code],
        cwd=FINANCE_SCRIPTS,
        env=_finance_env(base),
        label="isolated Finance path check",
    )
    return json.loads(stdout.strip().splitlines()[-1])


def _start(
    command: list[str], *, cwd: Path, env: dict[str, str], log: Path
) -> subprocess.Popen[str]:
    handle = log.open("w", encoding="utf-8")
    return subprocess.Popen(  # noqa: S603 - fixed local tool invocations only
        command,
        cwd=cwd,
        env=env,
        stdout=handle,
        stderr=subprocess.STDOUT,
        text=True,
    )


def _stop(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return
    subprocess.run(  # noqa: S603 - fixed taskkill command
        ["taskkill", "/PID", str(process.pid), "/T", "/F"],  # noqa: S607 - Windows system tool
        capture_output=True,
        check=False,
    )
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


def main() -> int:
    for port in (8000, 3000, FINANCE_PORT):
        _assert_port_free(port)

    (BACKEND_ROOT / "var").mkdir(parents=True, exist_ok=True)
    base = Path(tempfile.mkdtemp(prefix="stage5d-finance-", dir=BACKEND_ROOT / "var"))
    finance_process: subprocess.Popen[str] | None = None
    backend_process: subprocess.Popen[str] | None = None
    frontend_process: subprocess.Popen[str] | None = None
    result: dict[str, Any] = {}
    try:
        _seed_finance(base)
        paths = _finance_paths(base)
        for name, value in paths.items():
            if not Path(value).resolve().is_relative_to(base.resolve()):
                raise RuntimeError(f"isolated Finance {name} escaped the temp base: {value}")
        key_id, secret = _create_key(base)

        loaded = Settings()
        runtime_dsn = loaded.test_database_dsn
        migration_dsn = loaded.test_migration_dsn
        if runtime_dsn is None or migration_dsn is None:
            raise RuntimeError("The isolated Commerce test database DSNs are not configured.")
        from pydantic import SecretStr

        settings = Settings(
            environment="test",
            database_url=SecretStr(runtime_dsn),
            database_migration_url=SecretStr(migration_dsn),
            finance_integration_enabled=True,
            finance_integration_base_url=f"http://127.0.0.1:{FINANCE_PORT}",
            finance_integration_key_id=SecretStr(key_id),
            finance_integration_secret=SecretStr(secret),
            finance_integration_timeout_seconds=2.0,
        )
        world = _seed_commerce(settings)

        finance_env = _finance_env(
            base,
            TOUCHE_INTEGRATION_ENABLED="true",
            FINANS_UI_PORT=str(FINANCE_PORT),
        )
        finance_process = _start(
            [FINANCE_PYTHON, "-3.12", "finans_asistani_sunucu.py"],
            cwd=FINANCE_SCRIPTS,
            env=finance_env,
            log=base / "finance-server.log",
        )
        _wait(
            f"http://127.0.0.1:{FINANCE_PORT}/api/health",
            timeout=45,
            label="isolated Finance server",
        )

        commerce_env = {
            **os.environ,
            "TOUCHE_ENVIRONMENT": "test",
            "TOUCHE_DATABASE_URL": runtime_dsn,
            "TOUCHE_DATABASE_MIGRATION_URL": migration_dsn,
            "TOUCHE_SESSION_COOKIE_SECURE": "false",
            "TOUCHE_FINANCE_INTEGRATION_ENABLED": "true",
            "TOUCHE_FINANCE_INTEGRATION_BASE_URL": f"http://127.0.0.1:{FINANCE_PORT}",
            "TOUCHE_FINANCE_INTEGRATION_KEY_ID": key_id,
            "TOUCHE_FINANCE_INTEGRATION_SECRET": secret,
            "TOUCHE_FINANCE_INTEGRATION_TIMEOUT_SECONDS": "2",
        }
        _run(
            [
                sys.executable,
                "-m",
                "app.cli",
                "finance-map",
                "set",
                "--company",
                world["company_a_name"],
                "--finance-company",
                "gursar_mimarlik",
                "--actor",
                world["email"],
            ],
            cwd=BACKEND_ROOT,
            env=commerce_env,
            label="explicit Finance mapping CLI",
        )

        backend_process = _start(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
                "--no-server-header",
            ],
            cwd=BACKEND_ROOT,
            env=commerce_env,
            log=base / "commerce-api.log",
        )
        _wait(f"{COMMERCE_API}/api/v1/health/live", timeout=30, label="Commerce API")
        frontend_env = {
            **commerce_env,
            "NEXT_PUBLIC_API_BASE_URL": COMMERCE_API,
            "API_INTERNAL_BASE_URL": COMMERCE_API,
        }
        frontend_process = _start(
            ["npm.cmd", "run", "dev", "--", "-p", "3000"],
            cwd=FRONTEND_ROOT,
            env=frontend_env,
            log=base / "commerce-frontend.log",
        )
        _wait(f"{FRONTEND}/login", timeout=60, label="Commerce frontend")

        db_hash_before = _sha256(Path(paths["db"]))
        workbook_hash_before = _sha256(Path(paths["workbook"]))
        result = _acceptance(
            world=world,
            key_id=key_id,
            secret=secret,
            finance_db=Path(paths["db"]),
            finance_workbook=Path(paths["workbook"]),
            db_hash_before=db_hash_before,
            workbook_hash_before=workbook_hash_before,
        )
        result["verification"] = "ISOLATED_HTTP_VERIFIED"
        result["isolated_base"] = str(base)
        result["finance_paths"] = paths
        print(json.dumps(result, indent=2, ensure_ascii=True, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"VERIFICATION_FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        for log_name in ("finance-server.log", "commerce-api.log", "commerce-frontend.log"):
            log_path = base / log_name
            if log_path.exists():
                print(f"--- {log_name} ---", file=sys.stderr)
                print(
                    log_path.read_text(encoding="utf-8", errors="replace")[-4000:],
                    file=sys.stderr,
                )
        return 1
    finally:
        _stop(frontend_process)
        _stop(backend_process)
        _stop(finance_process)
        if "--keep-isolated" not in sys.argv:
            shutil.rmtree(base, ignore_errors=True)


def _acceptance(
    *,
    world: dict[str, Any],
    key_id: str,
    secret: str,
    finance_db: Path,
    finance_workbook: Path,
    db_hash_before: str,
    workbook_hash_before: str,
) -> dict[str, Any]:
    client = Client()
    texts: list[str] = []

    status, login_body, login_text = client.request(
        "POST",
        f"{COMMERCE_API}/api/v1/auth/login",
        payload={"email": world["email"], "password": PASSWORD},
        headers={"Origin": ORIGIN},
    )
    texts.append(login_text)
    if status != 200:
        raise AssertionError(f"Commerce login failed: {status} {login_text}")
    csrf = str(login_body["session"]["csrf_token"])
    if login_body["session"]["company"] is not None:
        raise AssertionError("multi-company test user unexpectedly auto-selected a company")

    switched_status, switched_body, switched_text = client.request(
        "POST",
        f"{COMMERCE_API}/api/v1/session/company",
        payload={"company_id": world["company_a"]},
        headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
    )
    texts.append(switched_text)
    if switched_status != 200:
        raise AssertionError(f"company switch failed: {switched_status} {switched_text}")
    csrf = str(switched_body["session"]["csrf_token"])

    def get_api(path: str, expected: int = 200) -> tuple[dict[str, Any], str]:
        response_status, payload, text = client.request("GET", f"{COMMERCE_API}{path}")
        texts.append(text)
        if response_status != expected:
            raise AssertionError(f"GET {path}: expected {expected}, got {response_status}: {text}")
        return payload, text

    status_body, _ = get_api("/api/v1/finance/status")
    if status_body["state"] != "connected":
        raise AssertionError(f"Finance status was not connected: {status_body}")
    if status_body["mapping"]["finance_company_id"] != "gursar_mimarlik":
        raise AssertionError("explicit Finance mapping was not returned")
    if not {"EUR", "TL"}.issubset(set(status_body["available_currencies"])):
        raise AssertionError("Finance currencies were not discovered")

    capabilities_body, _ = get_api("/api/v1/finance/capabilities")
    if capabilities_body["finance_company_id"] != "gursar_mimarlik":
        raise AssertionError("capabilities did not use the explicit mapping")
    if "company_ids" in capabilities_body:
        raise AssertionError("capabilities leaked the Finance key's company list")

    summary_body, _ = get_api("/api/v1/finance/summary?currency=TL")
    if summary_body["currency"] != "TL" or summary_body["data_through"] != "2026-02-21":
        raise AssertionError(f"unexpected Finance summary: {summary_body}")
    if summary_body["balances"]["cash"]["amount_kurus"] != 500_000:
        raise AssertionError("Finance cash source amount was not preserved")

    accounts_body, _ = get_api(
        "/api/v1/finance/accounts?currency=TL&from=2026-01-01&to=2026-02-28&limit=2&offset=0"
    )
    if accounts_body["page"]["limit"] != 2 or not accounts_body["accounts"]:
        raise AssertionError("accounts pagination or rows were not returned")
    if not any(row["account_code"] == "120" for row in accounts_body["accounts"]):
        raise AssertionError("receivable account 120 was not returned")

    receivable_body, _ = get_api("/api/v1/finance/aging?type=receivable&currency=TL")
    payable_body, _ = get_api("/api/v1/finance/aging?type=payable&currency=TL")
    if receivable_body["account"] != "120" or payable_body["account"] != "320":
        raise AssertionError("aging did not preserve the Finance account sides")
    if not receivable_body["items"] or not receivable_body["items"][0]["open_items"]:
        raise AssertionError("receivable aging did not expose open Finance source ids")

    missing_currency, missing_currency_text = get_api("/api/v1/finance/summary", expected=409)
    texts.append(missing_currency_text)
    if missing_currency["error"]["code"] != "FINANCE_CURRENCY_REQUIRED":
        raise AssertionError(f"missing currency was not preserved: {missing_currency}")

    get_api("/api/v1/dashboard/summary")
    get_api("/api/v1/integrations/finance/status")

    overview_status, _overview_body, overview_text = client.request(
        "GET", f"{FRONTEND}/finance?currency=TL"
    )
    texts.append(overview_text)
    if overview_status != 200:
        raise AssertionError(f"frontend overview failed: {overview_status}")
    if "CONNECTED" not in overview_text or "gursar_mimarlik" not in overview_text:
        raise AssertionError("frontend did not render the connected mapped company")

    accounts_page_status, _accounts_page_body, accounts_page_text = client.request(
        "GET", f"{FRONTEND}/finance?view=accounts&currency=TL"
    )
    texts.append(accounts_page_text)
    if accounts_page_status != 200 or "120" not in accounts_page_text:
        raise AssertionError("frontend did not render Finance accounts")

    receivables_page_status, _receivables_body, receivables_page_text = client.request(
        "GET", f"{FRONTEND}/finance?view=receivables&currency=TL"
    )
    texts.append(receivables_page_text)
    if receivables_page_status != 200 or "Customer A" not in receivables_page_text:
        raise AssertionError("frontend did not render receivable aging")

    payables_page_status, _payables_body, payables_page_text = client.request(
        "GET", f"{FRONTEND}/finance?view=payables&currency=TL"
    )
    texts.append(payables_page_text)
    if payables_page_status != 200 or "Supplier B" not in payables_page_text:
        raise AssertionError("frontend did not render payable aging")

    stage5d, stage5_context = _stage5d_acceptance(world)
    stage5e = _stage5e_acceptance(world, stage5_context)
    texts.extend(stage5_context["texts"])

    switched_b_status, _switched_b_body, switched_b_text = client.request(
        "POST",
        f"{COMMERCE_API}/api/v1/session/company",
        payload={"company_id": world["company_b"]},
        headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
    )
    texts.append(switched_b_text)
    if switched_b_status != 200:
        raise AssertionError(f"cross-tenant company switch failed: {switched_b_text}")
    b_status, _ = get_api("/api/v1/finance/status")
    if b_status["state"] != "not_configured" or b_status["mapping"] is not None:
        raise AssertionError(f"other tenant saw a Finance mapping: {b_status}")
    b_summary, b_summary_text = get_api("/api/v1/finance/summary?currency=TL", expected=409)
    texts.append(b_summary_text)
    if b_summary["error"]["code"] != "FINANCE_NOT_CONFIGURED":
        raise AssertionError(f"other tenant summary was not refused: {b_summary}")
    if "gursar_mimarlik" in b_summary_text:
        raise AssertionError("other tenant response leaked the mapped Finance company")

    post_status, _post_body, post_text = client.request(
        "POST",
        f"{COMMERCE_API}/api/v1/finance/summary?currency=TL",
        headers={"Origin": ORIGIN},
    )
    texts.append(post_text)
    if post_status != 405:
        raise AssertionError(f"Finance write-shaped route was not rejected: {post_status}")

    joined = "\n".join(texts)
    if key_id in joined or secret in joined:
        raise AssertionError("Finance credentials leaked into a Commerce response")

    db_hash_after = _sha256(finance_db)
    workbook_hash_after = _sha256(finance_workbook)
    if db_hash_after != db_hash_before or workbook_hash_after != workbook_hash_before:
        raise AssertionError("isolated Finance source changed during read-only acceptance")
    return {
        "finance_company": "gursar_mimarlik",
        "currencies": status_body["available_currencies"],
        "summary_currency": summary_body["currency"],
        "accounts_returned": len(accounts_body["accounts"]),
        "receivable_items": len(receivable_body["items"]),
        "payable_items": len(payable_body["items"]),
        "finance_frontend_routes": ["overview", "accounts", "receivables", "payables"],
        "stage5d": stage5d,
        "stage5e": stage5e,
        "cross_tenant_isolated": True,
        "write_route_rejected": post_status,
        "credentials_in_responses": False,
        "finance_db_sha256": db_hash_after,
        "finance_workbook_sha256": workbook_hash_after,
        "finance_db_unchanged": True,
        "finance_workbook_unchanged": True,
    }


if __name__ == "__main__":
    raise SystemExit(main())
