"""ORM model registry.

Importing this package registers every model on ``Base.metadata`` so Alembic
(and tests) see the complete schema.
"""

from app.db.models.base import SCHEMA, Base
from app.db.models.outbox import OutboxEvent

__all__ = ["SCHEMA", "Base", "OutboxEvent"]
