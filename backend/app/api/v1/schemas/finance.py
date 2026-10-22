"""Read-only Finance integration response schemas (Stage 5C).

Amounts are Finance decimal strings plus integer kuruş. The API never converts,
rounds, aggregates across currencies or reconstructs a financial value.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FinanceModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class FinanceMoney(FinanceModel):
    amount: str = Field(description="Finance decimal string, unchanged.")
    amount_kurus: int = Field(description="Finance integer kuruş representation.")


class FinancePage(FinanceModel):
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    total: int = Field(ge=0)
    next_offset: int | None = Field(default=None, ge=0)


class FinanceMapping(FinanceModel):
    finance_company_id: str | None = None
    finance_company_name: str | None = None
    status: Literal["pending", "verified", "disabled", "invalid"] | None = None
    configured_at: datetime | None = None
    last_verified_at: datetime | None = None


class FinanceStatusResponse(FinanceModel):
    state: Literal[
        "not_configured", "disabled", "connected", "degraded", "unavailable", "auth_error"
    ]
    detail: str
    checked_at: datetime
    latency_ms: float = Field(ge=0)
    mapping: FinanceMapping | None = None
    finance_status: str | None = None
    available_currencies: list[str] = Field(default_factory=list)
    data_through: date | None = None
    finance_request_id: str | None = None
    scope: Literal["finance_read"] = "finance_read"
    read_only: Literal[True] = True
    accounting_writes_enabled: Literal[False] = False


class FinanceCurrencySupport(FinanceModel):
    mode: str
    available: list[str] = Field(default_factory=list)
    aggregation: bool
    conversion: bool


class FinanceCapabilitiesResponse(FinanceModel):
    finance_company_id: str
    company_name: str
    contract_version: str
    scopes: list[str]
    max_page: int = Field(ge=1)
    endpoints: list[str]
    currency_support: FinanceCurrencySupport
    unsupported: list[str]
    limitations: list[str]
    available_currencies: list[str]
    data_through: date | None = None
    source: Literal["finance_ledger"] = "finance_ledger"
    finance_request_id: str | None = None
    fetched_at: datetime
    read_only: Literal[True] = True
    accounting_writes_enabled: Literal[False] = False


class FinanceLedger(FinanceModel):
    document_count: int = Field(ge=0)
    line_count: int = Field(ge=0)
    first_date: date | None = None
    last_date: date | None = None


class FinanceBalances(FinanceModel):
    cash: FinanceMoney
    receivables: FinanceMoney
    payables: FinanceMoney
    revenue: FinanceMoney
    cost: FinanceMoney
    gross_profit: FinanceMoney


class FinanceSummaryResponse(FinanceModel):
    company_id: str
    name: str
    holding_id: str | None = None
    active: bool
    as_of: date | None = None
    data_through: date | None = None
    currency: str | None = None
    currencies: list[str]
    source: Literal["finance_ledger"] = "finance_ledger"
    ledger: FinanceLedger
    balances: FinanceBalances
    finance_request_id: str | None = None
    fetched_at: datetime
    read_only: Literal[True] = True
    accounting_writes_enabled: Literal[False] = False


class FinanceAccount(FinanceModel):
    account_code: str
    name: str
    type: str
    debit: FinanceMoney
    credit: FinanceMoney
    balance: FinanceMoney


class FinanceAccountsResponse(FinanceModel):
    company_id: str
    from_date: date
    as_of: date
    currency: str | None = None
    accounts: list[FinanceAccount]
    page: FinancePage
    source: Literal["finance_ledger"] = "finance_ledger"
    finance_request_id: str | None = None
    fetched_at: datetime
    read_only: Literal[True] = True
    accounting_writes_enabled: Literal[False] = False


class FinanceAgingBuckets(FinanceModel):
    not_due: FinanceMoney
    days_1_30: FinanceMoney
    days_31_60: FinanceMoney
    days_61_90: FinanceMoney
    days_over_90: FinanceMoney


class FinanceOpenItem(FinanceModel):
    source_id: str
    source: str
    due_date: date | None = None
    remaining: FinanceMoney


class FinanceAgingItem(FinanceModel):
    counterparty: str
    counterparty_key_type: Literal["ledger.cari"]
    buckets: FinanceAgingBuckets
    total: FinanceMoney
    advance: FinanceMoney
    overdue: bool
    overdue_amount: FinanceMoney
    open_items: list[FinanceOpenItem]


class FinanceAgingSummary(FinanceModel):
    total: FinanceMoney
    overdue: FinanceMoney
    overdue_ratio: float


class FinanceAgingResponse(FinanceModel):
    company_id: str
    type: Literal["receivable", "payable"]
    account: str
    as_of: date | None = None
    currency: str | None = None
    summary: FinanceAgingSummary
    items: list[FinanceAgingItem]
    page: FinancePage
    source: Literal["finance_ledger"] = "finance_ledger"
    finance_request_id: str | None = None
    fetched_at: datetime
    read_only: Literal[True] = True
    accounting_writes_enabled: Literal[False] = False
