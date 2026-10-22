"""Outbound integration boundaries.

Stage 5A deliberately contains **one** integration surface: a read-only health
probe for TOUCHE FINANCE.  Commerce never posts accounting entries, invoices or
payments; TOUCHE FINANCE remains the financial source of truth
(``docs/DECISIONS.md`` ADR-038/ADR-039).

Adding a business-data adapter here requires a verified Finance interface and a
new ADR; a client that merely assumes an endpoint exists is not acceptable.
"""

from __future__ import annotations
