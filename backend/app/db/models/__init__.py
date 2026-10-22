"""ORM model registry.

Importing this package registers every model on ``Base.metadata`` so Alembic
(and tests) see the complete schema.
"""

from app.db.models.audit import AuditAction, AuditActorType, AuditOutcome, AuditRecord
from app.db.models.base import SCHEMA, Base
from app.db.models.identity import (
    Company,
    CompanyStatus,
    LoginAttempt,
    Membership,
    MembershipStatus,
    User,
    UserSession,
    UserStatus,
)
from app.db.models.outbox import OutboxEvent
from app.db.models.sourcing import (
    CostBasis,
    CostType,
    FxRateSnapshot,
    Incoterm,
    PricingCostComponent,
    PricingScenario,
    RfqStatus,
    SalesQuote,
    SalesQuoteItem,
    SalesQuoteRevision,
    SalesQuoteStatus,
    ScenarioStatus,
    SupplierQuote,
    SupplierQuoteItem,
    SupplierQuoteRevision,
    SupplierQuoteStatus,
    SupplierRfq,
    SupplierRfqItem,
    SupplierRfqRevision,
    VerificationStatus,
)
from app.db.models.tenant_data import CompanySettingEntry, CompanySettings, IdempotencyRecord
from app.db.models.trade import (
    Counterparty,
    CounterpartyType,
    Deal,
    DealItem,
    DealStatus,
    DealTransition,
    Product,
    ProductUnit,
    RecordStatus,
)

__all__ = [
    "SCHEMA",
    "AuditAction",
    "AuditActorType",
    "AuditOutcome",
    "AuditRecord",
    "Base",
    "Company",
    "CompanySettingEntry",
    "CompanySettings",
    "CompanyStatus",
    "CostBasis",
    "CostType",
    "Counterparty",
    "CounterpartyType",
    "Deal",
    "DealItem",
    "DealStatus",
    "DealTransition",
    "FxRateSnapshot",
    "IdempotencyRecord",
    "Incoterm",
    "LoginAttempt",
    "Membership",
    "MembershipStatus",
    "OutboxEvent",
    "PricingCostComponent",
    "PricingScenario",
    "Product",
    "ProductUnit",
    "RecordStatus",
    "RfqStatus",
    "SalesQuote",
    "SalesQuoteItem",
    "SalesQuoteRevision",
    "SalesQuoteStatus",
    "ScenarioStatus",
    "SupplierQuote",
    "SupplierQuoteItem",
    "SupplierQuoteRevision",
    "SupplierQuoteStatus",
    "SupplierRfq",
    "SupplierRfqItem",
    "SupplierRfqRevision",
    "User",
    "UserSession",
    "UserStatus",
    "VerificationStatus",
]

