"""The tool registry and the executor that stands between the model and the business.

A model never touches a service. It names a tool and arguments; the executor then,
for every single call and in this order:

1. refuses an unknown or ``BLOCKED`` tool (audited as denied);
2. refuses arguments the provider sent as invalid JSON;
3. re-reads the caller's *current* membership and refuses a tool whose permission the
   caller no longer holds (a revoked member loses access mid-conversation);
4. validates the arguments against the tool's schema — ``additionalProperties`` is
   always false, so a ``company_id`` argument is rejected, never honoured;
5. runs the read-only handler with the server-chosen company and user;
6. withholds instruction-like text, bounds the size and registers the evidence.

The registry also lists the actions that can never be performed (``BLOCKED``): they
are not offered to the model, and a request for one is a recorded safety event.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import UUID

from app.ai.evidence import EvidenceItem, EvidenceRegistry
from app.ai.safety import Sanitiser
from app.ai.types import ToolCall, ToolSpec
from app.core.config import Settings
from app.core.errors import ApiError, NotFoundError
from app.db.engine import Database
from app.security.permissions import Permission

logger = logging.getLogger("app.ai.tools")

_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


class ToolClass(StrEnum):
    READ_ONLY = "READ_ONLY"
    DRAFT_PROPOSAL = "DRAFT_PROPOSAL"
    REQUIRES_HUMAN_APPROVAL = "REQUIRES_HUMAN_APPROVAL"
    BLOCKED = "BLOCKED"


class ToolOutcome(StrEnum):
    OK = "OK"
    DENIED = "DENIED"
    INVALID = "INVALID"
    ERROR = "ERROR"
    LIMITED = "LIMITED"


#: Actions that are never available to the AI, whatever the user's role. The names are
#: what a misbehaving model is most likely to ask for; any other unknown name is denied
#: in the same way.
BLOCKED_ACTIONS: dict[str, str] = {
    "send_email": "Sending messages needs a person; drafts are proposals only.",
    "send_message": "Sending messages needs a person; drafts are proposals only.",
    "create_payment": "Bank payments are outside the AI's authority.",
    "approve_payment": "Financial approval is a human decision (finance.approve).",
    "approve_finance": "Financial approval is a human decision (finance.approve).",
    "post_journal_entry": "Accounting postings are not available (Finance is read-only).",
    "create_journal_entry": "Accounting postings are not available (Finance is read-only).",
    "mark_deal_won": "A deal is won only through a recorded customer acceptance.",
    "accept_customer_quote": "Customer acceptance is evidence recorded by a person.",
    "sign_contract": "Contract signature is outside the AI's authority.",
    "create_sales_order": "Orders are created by a person from an accepted quote.",
    "delete_record": "Deletion is not available.",
    "execute_sql": "Arbitrary SQL is not available.",
    "run_shell": "Shell access is not available.",
    "read_file": "Filesystem access is not available.",
    "fetch_url": "Network access is not available.",
}

ToolHandler = Callable[["ToolContext", dict[str, Any]], "ToolResult"]


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]
    permission: Permission
    handler: ToolHandler
    tool_class: ToolClass = ToolClass.READ_ONLY

    def spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description=self.description, parameters=self.parameters)


@dataclass
class ToolResult:
    """What a handler returns: compact data for the model plus the evidence behind it."""

    data: dict[str, Any]
    evidence: list[EvidenceItem] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)
    truncated: bool = False


@dataclass
class ToolContext:
    """Everything a handler may use. The company and user are chosen by the server."""

    company_id: UUID
    user_id: UUID
    database: Database
    settings: Settings
    sanitiser: Sanitiser = field(default_factory=Sanitiser)

    @property
    def max_items(self) -> int:
        return self.settings.ai_max_list_items


@dataclass(frozen=True)
class ToolExecution:
    """The outcome of one call: the message for the model and the log row."""

    content: str
    outcome: ToolOutcome
    tool_name: str
    tool_class: ToolClass
    arguments: dict[str, Any]
    result_meta: dict[str, Any]
    result_chars: int
    duration_ms: int
    error_code: str | None
    safety_flags: tuple[str, ...] = ()


# ----------------------------------------------------------------- validation
class ArgumentError(ValueError):
    """The arguments do not satisfy the tool's schema."""


def validate_arguments(schema: dict[str, Any], arguments: dict[str, Any]) -> dict[str, Any]:
    """Validate against the small JSON-Schema subset the tools use and normalise."""
    properties: dict[str, dict[str, Any]] = schema.get("properties", {})
    unknown = sorted(set(arguments) - set(properties))
    if unknown:
        raise ArgumentError(f"unexpected argument: {unknown[0]}")
    for name in schema.get("required", []):
        if name not in arguments or arguments[name] in (None, ""):
            raise ArgumentError(f"missing argument: {name}")
    clean: dict[str, Any] = {}
    for name, value in arguments.items():
        if value is None or value == "":
            continue
        rule = properties[name]
        kind = rule.get("type")
        if kind == "string":
            if not isinstance(value, str):
                raise ArgumentError(f"{name} must be a string")
            text = value.strip()
            if len(text) > int(rule.get("maxLength", 200)):
                raise ArgumentError(f"{name} is too long")
            if rule.get("format") == "uuid" and not _UUID.match(text):
                raise ArgumentError(f"{name} must be a UUID")
            if "enum" in rule and text not in rule["enum"]:
                raise ArgumentError(f"{name} is not an allowed value")
            if "pattern" in rule and not re.match(rule["pattern"], text):
                raise ArgumentError(f"{name} has an invalid format")
            clean[name] = text
        elif kind == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                raise ArgumentError(f"{name} must be an integer")
            if value < int(rule.get("minimum", 0)) or value > int(rule.get("maximum", 1_000)):
                raise ArgumentError(f"{name} is out of range")
            clean[name] = value
        elif kind == "boolean":
            if not isinstance(value, bool):
                raise ArgumentError(f"{name} must be a boolean")
            clean[name] = value
        else:  # pragma: no cover - schemas are authored in this repository
            raise ArgumentError(f"{name} has an unsupported type")
    return clean


def uuid_of(arguments: dict[str, Any], name: str) -> UUID | None:
    value = arguments.get(name)
    return UUID(value) if value else None


# ------------------------------------------------------------------- registry
class ToolRegistry:
    def __init__(self, tools: list[ToolDefinition] | None = None) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        for tool in tools or []:
            self.register(tool)

    def register(self, tool: ToolDefinition) -> None:
        if tool.tool_class is ToolClass.BLOCKED:
            raise ValueError("a blocked action cannot be registered as a callable tool")
        if tool.name in self._tools or tool.name in BLOCKED_ACTIONS:
            raise ValueError(f"duplicate or blocked tool name: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def all(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    def specs_for(self, permissions: frozenset[Permission]) -> tuple[ToolSpec, ...]:
        """Only the tools the caller may use are even described to the model."""
        return tuple(t.spec() for t in self._tools.values() if t.permission in permissions)


# -------------------------------------------------------------------- results
def _longest_list(container: dict[str, Any]) -> list[Any] | None:
    best: list[Any] | None = None
    for value in container.values():
        if isinstance(value, list) and len(value) > 1 and (best is None or len(value) > len(best)):
            best = value
    return best


def _fit(
    data: dict[str, Any], evidence: list[EvidenceItem], budget: int
) -> tuple[dict[str, Any], list[EvidenceItem], bool]:
    """Drop trailing list items until the serialised result fits ``budget`` characters."""
    truncated = False
    evidence = list(evidence)

    def size() -> int:
        return len(json.dumps(data, default=str)) + 650 * len(evidence)

    while size() > budget:
        target = _longest_list(data)
        if target is not None and len(target) >= len(evidence):
            target.pop()
        elif evidence:
            evidence.pop()
        elif target is not None:
            target.pop()
        else:
            break
        truncated = True
    return data, evidence, truncated


class ToolExecutor:
    """Runs one tool call under every guard (see the module docstring)."""

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        settings: Settings,
        database: Database,
        permissions_loader: Callable[[UUID, UUID], frozenset[Permission]],
    ) -> None:
        self._registry = registry
        self._settings = settings
        self._database = database
        self._permissions = permissions_loader

    def execute(
        self,
        call: ToolCall,
        *,
        company_id: UUID,
        user_id: UUID,
        evidence: EvidenceRegistry,
        within_limit: bool = True,
    ) -> ToolExecution:
        started = time.monotonic()

        def finish(
            outcome: ToolOutcome,
            tool_class: ToolClass,
            *,
            error: str | None = None,
            message: str | None = None,
            arguments: dict[str, Any] | None = None,
            flags: tuple[str, ...] = (),
        ) -> ToolExecution:
            payload = {"tool": call.name, "ok": False, "error": error, "message": message}
            content = json.dumps(payload)
            return ToolExecution(
                content=content,
                outcome=outcome,
                tool_name=call.name[:64],
                tool_class=tool_class,
                arguments=arguments if arguments is not None else {},
                result_meta={"error": error},
                result_chars=len(content),
                duration_ms=int((time.monotonic() - started) * 1000),
                error_code=error,
                safety_flags=flags,
            )

        tool = self._registry.get(call.name)
        if tool is None:
            blocked = call.name in BLOCKED_ACTIONS
            return finish(
                ToolOutcome.DENIED,
                ToolClass.BLOCKED,
                error="TOOL_BLOCKED" if blocked else "TOOL_UNKNOWN",
                message=BLOCKED_ACTIONS.get(call.name, "This tool does not exist."),
                flags=("BLOCKED_TOOL_REQUESTED",) if blocked else ("UNKNOWN_TOOL_REQUESTED",),
            )
        if not within_limit:
            return finish(
                ToolOutcome.LIMITED,
                tool.tool_class,
                error="TOOL_CALL_LIMIT",
                message=(
                    "The tool-call limit for this request was reached. Answer with what you have."
                ),
            )
        if call.arguments_error:
            return finish(
                ToolOutcome.INVALID,
                tool.tool_class,
                error="INVALID_ARGUMENTS",
                message=call.arguments_error,
            )
        if tool.permission not in self._permissions(user_id, company_id):
            return finish(
                ToolOutcome.DENIED,
                tool.tool_class,
                error="PERMISSION_DENIED",
                message="The signed-in user may not use this tool in the active company.",
                flags=("PERMISSION_DENIED",),
            )
        try:
            arguments = validate_arguments(tool.parameters, call.arguments)
        except ArgumentError as exc:
            flags = ("COMPANY_ID_ARGUMENT",) if "company" in str(exc) else ()
            return finish(
                ToolOutcome.INVALID,
                tool.tool_class,
                error="INVALID_ARGUMENTS",
                message=str(exc),
                flags=flags,
            )

        context = ToolContext(
            company_id=company_id,
            user_id=user_id,
            database=self._database,
            settings=self._settings,
        )
        try:
            result = tool.handler(context, arguments)
        except NotFoundError:
            return finish(
                ToolOutcome.ERROR,
                tool.tool_class,
                error="NOT_FOUND",
                message="No such record in the active company.",
                arguments=arguments,
            )
        except ApiError as exc:
            return finish(
                ToolOutcome.ERROR,
                tool.tool_class,
                error=str(exc.code),
                message="The request could not be completed.",
                arguments=arguments,
            )
        except Exception as exc:
            logger.error("ai.tool.failed", extra={"tool": tool.name, "error": type(exc).__name__})
            return finish(
                ToolOutcome.ERROR,
                tool.tool_class,
                error="TOOL_FAILED",
                message="The tool failed.",
                arguments=arguments,
            )

        cap = self._settings.ai_max_tool_result_chars
        data, items, truncated = _fit(result.data, result.evidence, cap)
        registered = [evidence.register(item, tool=tool.name) for item in items]
        evidence.absorb_numbers(data)
        for registered_item in registered:
            evidence.absorb_numbers(registered_item.item.facts_dict())
        notices = list(result.notices)
        if context.sanitiser.flags:
            notices.append("INSTRUCTION_LIKE_TEXT_WITHHELD")
        payload = {
            "tool": tool.name,
            "ok": True,
            "truncated": truncated or result.truncated,
            "notices": notices,
            "data": data,
            "evidence": [
                {
                    "id": r.id,
                    "entity_type": r.item.entity_type,
                    "entity_id": r.item.entity_id,
                    "reference": r.item.reference,
                    "label": r.item.label,
                    "basis": str(r.item.basis),
                    "as_of": r.item.as_of,
                    "completeness": r.item.completeness,
                    "facts": dict(r.item.facts),
                    "warnings": list(r.item.warnings),
                }
                for r in registered
            ],
        }
        content = json.dumps(payload, default=str, ensure_ascii=False)
        return ToolExecution(
            content=content,
            outcome=ToolOutcome.OK,
            tool_name=tool.name,
            tool_class=tool.tool_class,
            arguments=arguments,
            result_meta={
                "evidence": [r.id for r in registered],
                "truncated": truncated or result.truncated,
                "notices": notices,
            },
            result_chars=len(content),
            duration_ms=int((time.monotonic() - started) * 1000),
            error_code=None,
            safety_flags=tuple(f"INJECTION:{flag}" for flag in context.sanitiser.flags),
        )
