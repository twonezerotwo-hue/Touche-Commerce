"""Live check of the Finance integration API (read-only), summarised without leaking data.

Calls the six documented read-only endpoints with the integration key from the environment
(``TOUCHE_FINANCE_INTEGRATION_KEY_ID`` / ``..._SECRET``), then confirms that a write method and
a wrong secret are refused. It prints statuses, counts, currencies and the data-through date;
never the secret and never ledger amounts or counterparty names.

    backend\\.venv\\Scripts\\python.exe scripts\\finance_live_check.py [--base-url http://127.0.0.1:8765]

Exit 0 = FINANCE_LIVE_VERIFIED; 1 = a check failed; 2 = Finance or the key is not available.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from typing import Any

BASE_PATH = "/api/integration/v1"


def call(
    base: str, path: str, key: str, secret: str, *, method: str = "GET"
) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(  # noqa: S310 - loopback URL checked in main()
        f"{base}{BASE_PATH}{path}",
        method=method,
        headers={"X-Touche-Integration-Key": key, "X-Touche-Integration-Secret": secret},
        data=b"{}" if method != "GET" else None,
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", "replace")
        try:
            return error.code, json.loads(body)
        except json.JSONDecodeError:
            return error.code, {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    args = parser.parse_args()
    if not args.base_url.startswith(("http://127.0.0.1", "http://localhost")):
        print("Refusing: the Finance integration is loopback only.")
        return 1
    key = os.environ.get("TOUCHE_FINANCE_INTEGRATION_KEY_ID", "")
    secret = os.environ.get("TOUCHE_FINANCE_INTEGRATION_SECRET", "")
    if not key or not secret:
        print("FINANCE_KEY_MISSING: set the integration key id and secret in the environment.")
        return 2

    failures: list[str] = []

    def check(condition: bool, label: str) -> None:
        print(f"  [{'ok' if condition else 'FAIL'}] {label}")
        if not condition:
            failures.append(label)

    status, health = call(args.base_url, "/health", key, secret)
    if status != 200:
        print(f"FINANCE_UNAVAILABLE: /health answered {status}.")
        return 2
    data = health.get("data", {})
    check(health.get("meta", {}).get("read_only") is True, "responses declare read_only")
    check(data.get("ledger_readable") is True, "ledger readable, no missing tables")
    check(
        data.get("pending_recovery") == 0 and data.get("needs_review") == 0,
        "no journal in recovery",
    )
    print(
        f"  health: status={data.get('status')} data_through={data.get('data_through')} "
        f"counts={data.get('counts')}"
    )

    status, capabilities = call(args.base_url, "/capabilities", key, secret)
    caps = capabilities.get("data", {})
    check(status == 200 and caps.get("scopes") == ["finance.read"], "single finance.read scope")
    companies = caps.get("company_ids", [])
    check(len(companies) >= 1, f"{len(companies)} authorised company ids")

    status, listing = call(args.base_url, "/companies", key, secret)
    items = listing.get("data", {}).get("companies", [])
    check(status == 200 and len(items) == len(companies), "company list matches the key")
    for item in items:
        print(
            f"  company {item['id']}: currencies={item.get('currencies')} "
            f"active={item.get('active')} through={item.get('data_through')}"
        )

    for item in items:
        cid = item["id"]
        currencies = item.get("currencies") or []
        query = f"?currency={currencies[0]}" if len(currencies) > 0 else ""
        status, summary = call(args.base_url, f"/companies/{cid}/summary{query}", key, secret)
        ledger = summary.get("data", {}).get("ledger", {})
        check(status == 200, f"{cid}: summary 200, {ledger.get('document_count')} documents")
        status, accounts = call(args.base_url, f"/companies/{cid}/accounts{query}", key, secret)
        total = accounts.get("data", {}).get("page", {}).get("total")
        check(status == 200, f"{cid}: accounts 200, {total} accounts")
        for kind in ("receivable", "payable"):
            joiner = "&" if query else "?"
            status, _aging = call(
                args.base_url, f"/companies/{cid}/aging{query}{joiner}type={kind}", key, secret
            )
            check(status == 200, f"{cid}: {kind} aging 200")

    status, _ = call(args.base_url, "/companies", key, secret, method="POST")
    check(status == 405, "a POST is refused (405 READ_ONLY)")
    status, _ = call(args.base_url, "/companies", key, "x" * 43)
    check(status in (401, 403), f"a wrong secret is refused ({status})")
    status, _ = call(args.base_url, "/companies/not_a_company/summary", key, secret)
    check(status in (403, 404), f"an unauthorised company is refused ({status})")

    if failures:
        print(f"FINANCE_LIVE_FAILED: {len(failures)} check(s) failed.")
        return 1
    print("FINANCE_LIVE_VERIFIED: Finance answered read-only for every authorised company.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
