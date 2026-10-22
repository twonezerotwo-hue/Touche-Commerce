"""Isolated HTTP acceptance verifier for Stage 5C.

The verifier never starts or points at the live Finance application. It creates a
temporary Finance base directory, initialises a synthetic SQLite ledger, creates a
temporary integration key, starts Finance on an isolated loopback port, starts
Commerce against the isolated test PostgreSQL database, and drives the real HTTP
APIs through a browser-like cookie jar.

Usage (from the Commerce repository):
    backend\\.venv\\Scripts\\python.exe backend\\scripts\\verify_finance_http.py
"""

from __future__ import annotations

import hashlib
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
PASSWORD = "Stage5C-Isolated-Horse-9"  # noqa: S105 - temporary isolated test account only
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
    seed = r'''
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
    con.commit()
finally:
    con.close()

print(f"ISOLATED_BASE={config.BASE_DIR}")
print(f"ISOLATED_DB={cekirdek.DB_PATH}")
print(f"ISOLATED_WORKBOOK={config.ana_excel_yolu()}")
'''
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
            "stage5c-isolated-http",
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
    company_a_name = f"Stage5C Commerce {suffix}"
    company_b_name = f"Stage5C Other {suffix}"
    email = f"stage5c-{suffix}@touche.example"
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
                display_name="Stage 5C Isolated Operator",
                password_hash=password_hash,
            )
            admin.grant_membership(
                session, user_id=user.id, company_id=company_a.id, role=Role.ADMIN
            )
            admin.grant_membership(
                session, user_id=user.id, company_id=company_b.id, role=Role.VIEWER
            )
            return {
                "company_a": str(company_a.id),
                "company_b": str(company_b.id),
                "company_a_name": company_a_name,
                "company_b_name": company_b_name,
                "user_id": str(user.id),
                "email": email,
            }
    finally:
        database.dispose()


class Client:
    def __init__(self) -> None:
        self.jar = CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar)
        )

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
            "User-Agent": "stage5c-isolated-verifier",
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

    @staticmethod
    def _json(text: str) -> dict[str, Any]:
        try:
            payload = json.loads(text)
            return payload if isinstance(payload, dict) else {}
        except json.JSONDecodeError:
            return {}


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
    base = Path(
        tempfile.mkdtemp(prefix="stage5c-finance-", dir=BACKEND_ROOT / "var")
    )
    finance_process: subprocess.Popen[str] | None = None
    backend_process: subprocess.Popen[str] | None = None
    frontend_process: subprocess.Popen[str] | None = None
    result: dict[str, Any] = {}
    try:
        _seed_finance(base)
        paths = _finance_paths(base)
        for name, value in paths.items():
            if not Path(value).resolve().is_relative_to(base.resolve()):
                raise RuntimeError(
                    f"isolated Finance {name} escaped the temp base: {value}"
                )
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
            raise AssertionError(
                f"GET {path}: expected {expected}, got {response_status}: {text}"
            )
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

    missing_currency, missing_currency_text = get_api(
        "/api/v1/finance/summary", expected=409
    )
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
    b_summary, b_summary_text = get_api(
        "/api/v1/finance/summary?currency=TL", expected=409
    )
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
        "frontend_routes": ["overview", "accounts", "receivables", "payables"],
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
