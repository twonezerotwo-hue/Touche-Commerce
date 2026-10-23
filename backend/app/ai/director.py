"""The Trade Director: admission checks, the bounded tool loop and the validated answer.

The loop is deliberately small and cannot run away:

* at most ``ai_max_model_steps`` model calls and ``ai_max_tool_calls_per_request`` tool
  calls per request, plus a token ceiling and a wall-clock deadline;
* cancellation is checked before every model call and tool call;
* once the tool allowance is spent the model is called without tools, so it must answer;
* the answer is parsed and validated against the evidence the tools returned, so the
  operator never sees a citation or a figure the system cannot trace to a record.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.ai.errors import (
    AIBudgetExceededError,
    AIDisabledError,
    AIInputTooLargeError,
    AIRunCancelledError,
    AITooManyRunsError,
    ProviderBadResponseError,
    ProviderTimeoutError,
)
from app.ai.evidence import (
    EvidenceRegistry,
    parse_model_json,
    unstructured_response,
    validate_response,
)
from app.ai.gateway import (
    AIGateway,
    CancelToken,
    RunBudget,
    RunLimiter,
    RunRegistry,
    usage_cost_usd,
)
from app.ai.prompts import PROMPT_VERSION, SYSTEM_PROMPT
from app.ai.proposals import NewProposal, extract_proposals
from app.ai.providers import build_provider
from app.ai.providers.base import ModelProvider
from app.ai.safety import untrusted
from app.ai.tools.readonly import build_registry
from app.ai.tools.registry import ToolExecutor, ToolRegistry
from app.ai.types import ModelMessage, ModelRequest, Usage
from app.core.config import Settings
from app.core.errors import ApiError, ErrorCode, ForbiddenError
from app.db.engine import Database
from app.db.models.ai import RunStatus
from app.security.permissions import Permission
from app.services.ai_office import (
    AiOfficeService,
    MessageRecord,
    RunFinish,
    RunRecord,
    current_permissions,
)

logger = logging.getLogger("app.ai.director")


@dataclass(frozen=True)
class RunRequest:
    """Everything the director needs about the caller. Chosen by the server."""

    company_id: UUID
    user_id: UUID
    company_name: str
    company_currency: str
    role: str
    request_id: str | None


class AIRuntime:
    """Process-wide AI collaborators, created once per application."""

    def __init__(
        self,
        settings: Settings,
        database: Database,
        *,
        provider: ModelProvider | None = None,
        tools: ToolRegistry | None = None,
    ) -> None:
        self.settings = settings
        self.database = database
        self.office = AiOfficeService(database)
        self.tools = tools or build_registry()
        self.provider: ModelProvider | None = provider
        if self.provider is None and settings.ai_enabled:
            self.provider = build_provider(settings)
        self.gateway = AIGateway(settings, self.provider) if self.provider else None
        self.limiter = RunLimiter(settings.ai_max_concurrent_runs)
        self.runs = RunRegistry()
        self.executor = ToolExecutor(
            self.tools,
            settings=settings,
            database=database,
            permissions_loader=lambda user_id, company_id: current_permissions(
                database, user_id, company_id
            ),
        )

    @property
    def enabled(self) -> bool:
        return self.settings.ai_enabled and self.provider is not None

    # ---------------------------------------------------------------- admission
    def submit(
        self, caller: RunRequest, *, conversation_id: UUID, text: str
    ) -> tuple[RunRecord, MessageRecord, CancelToken]:
        """Validate and record a request; the model is not called yet."""
        if not self.enabled or self.provider is None:
            raise AIDisabledError()
        settings = self.settings
        cleaned = text.strip()
        if not cleaned:
            raise AIInputTooLargeError("The message is empty.")
        if len(cleaned) > settings.ai_max_user_message_chars:
            raise AIInputTooLargeError()
        office = self.office
        office.expire_stale_runs(
            company_id=caller.company_id,
            older_than_seconds=int(settings.ai_run_deadline_seconds) + 60,
        )
        if (
            office.recent_run_count(company_id=caller.company_id, user_id=caller.user_id)
            >= settings.ai_max_runs_per_user_per_minute
        ):
            raise AITooManyRunsError("Too many AI requests in the last minute. Please wait.")
        usage = office.usage_today(company_id=caller.company_id)
        if (
            usage.tokens >= settings.ai_daily_token_budget
            or usage.cost_usd >= settings.ai_daily_cost_budget_usd
        ):
            raise AIBudgetExceededError("The daily AI budget for this company has been reached.")
        self.limiter.acquire()
        try:
            run, message = office.start_run(
                company_id=caller.company_id,
                user_id=caller.user_id,
                conversation_id=conversation_id,
                user_text=cleaned,
                provider=self.provider.name,
                model=self.provider.model,
                prompt_version=PROMPT_VERSION,
                is_external=self.provider.is_external,
                request_id=caller.request_id,
            )
        except Exception:
            self.limiter.release()
            raise
        token = self.runs.register(run.id, company_id=caller.company_id, user_id=caller.user_id)
        return run, message, token

    # ---------------------------------------------------------------- execution
    def execute(
        self, caller: RunRequest, run: RunRecord, user_text: str, cancel: CancelToken
    ) -> None:
        """Run the loop and always finish the run row, whatever happens."""
        director = _Loop(self, caller, run, user_text, cancel)
        try:
            finish = director.run()
        finally:
            self.runs.release(run.id)
            self.limiter.release()
        try:
            self.office.finish_run(
                company_id=caller.company_id,
                user_id=caller.user_id,
                run_id=run.id,
                finish=finish,
                request_id=caller.request_id,
            )
        except Exception as exc:
            logger.error("ai.run.finish_failed", extra={"error": type(exc).__name__})


@dataclass
class _Loop:
    runtime: AIRuntime
    caller: RunRequest
    run_record: RunRecord
    user_text: str
    cancel: CancelToken
    evidence: EvidenceRegistry = field(default_factory=EvidenceRegistry)
    flags: list[str] = field(default_factory=list)
    budget: RunBudget = field(init=False)

    def __post_init__(self) -> None:
        settings = self.runtime.settings
        self.budget = RunBudget(
            max_tokens=settings.ai_max_request_tokens,
            max_steps=settings.ai_max_model_steps,
            max_tool_calls=settings.ai_max_tool_calls_per_request,
        )

    # ------------------------------------------------------------------ helpers
    def _messages(self, history: list[tuple[str, str]]) -> list[ModelMessage]:
        name, name_flags = untrusted(self.caller.company_name, limit=80)
        self._flag(name_flags)
        context = (
            "SERVER CONTEXT (set by the server, not by the operator or any record):\n"
            f"- Active company: {name}\n"
            f"- Company currency: {self.caller.company_currency}\n"
            f"- Operator role: {self.caller.role}\n"
            f"- Today (UTC): {datetime.now(UTC).date().isoformat()}\n"
            "- Evidence ids (E1, E2, ...) exist only for this request; call tools again to "
            "cite records."
        )
        messages = [ModelMessage("system", f"{SYSTEM_PROMPT}\n{context}")]
        for role, content in history:
            messages.append(ModelMessage("user" if role == "USER" else "assistant", content))
        return messages

    def _flag(self, flags: Any) -> None:
        for flag in flags:
            if flag not in self.flags:
                self.flags.append(flag)

    def _deadline(self, started: float) -> None:
        if time.monotonic() - started > self.runtime.settings.ai_run_deadline_seconds:
            raise ProviderTimeoutError("The AI request exceeded its time limit.")

    def _finish(
        self,
        status: RunStatus,
        *,
        error: str | None = None,
        warnings: list[str] | None = None,
        text: str | None = None,
        structured: dict[str, Any] | None = None,
        evidence: list[dict[str, Any]] | None = None,
        proposals: list[NewProposal] | None = None,
    ) -> RunFinish:
        budget = self.budget
        cost = usage_cost_usd(
            self.runtime.settings, Usage(budget.used_input_tokens, budget.used_output_tokens)
        )
        return RunFinish(
            status=status,
            input_tokens=budget.used_input_tokens,
            output_tokens=budget.used_output_tokens,
            estimated_usage=budget.estimated,
            cost_usd=Decimal(cost),
            model_steps=budget.steps,
            tool_call_count=budget.tool_calls,
            provider_calls=budget.provider_calls,
            error_code=error,
            validation_warnings=warnings or [],
            safety_flags=list(self.flags),
            assistant_text=text,
            structured=structured,
            evidence=evidence or [],
            proposals=proposals or [],
        )

    # --------------------------------------------------------------------- loop
    def run(self) -> RunFinish:
        try:
            return self._run()
        except AIRunCancelledError:
            return self._finish(RunStatus.CANCELLED, error=str(ErrorCode.AI_RUN_CANCELLED))
        except ApiError as exc:
            return self._finish(RunStatus.FAILED, error=str(exc.code))
        except Exception as exc:
            logger.error("ai.run.failed", extra={"error": type(exc).__name__})
            return self._finish(RunStatus.FAILED, error=str(ErrorCode.INTERNAL_ERROR))

    def _run(self) -> RunFinish:
        runtime, caller = self.runtime, self.caller
        settings = runtime.settings
        gateway = runtime.gateway
        if gateway is None:
            raise AIDisabledError()
        permissions = current_permissions(runtime.database, caller.user_id, caller.company_id)
        if Permission.COMPANY_VIEW not in permissions:
            raise ForbiddenError()
        specs = runtime.tools.specs_for(permissions)

        history = runtime.office.recent_messages(
            company_id=caller.company_id,
            conversation_id=self.run_record.conversation_id,
            limit=settings.ai_max_context_messages,
        )
        messages = self._messages(history)
        started = time.monotonic()
        ordinal = 0
        final_text: str | None = None

        for _ in range(settings.ai_max_model_steps):
            self.cancel.check()
            self._deadline(started)
            self.budget.start_step()
            tools_allowed = self.budget.tool_calls < self.budget.max_tool_calls
            request = ModelRequest(
                messages=tuple(messages),
                tools=specs if tools_allowed else (),
                max_output_tokens=settings.ai_max_output_tokens,
                timeout_seconds=settings.ai_request_timeout_seconds,
                request_id=str(self.run_record.id),
            )
            response = gateway.complete(request, budget=self.budget, cancel=self.cancel)
            if response.tool_calls and tools_allowed:
                messages.append(ModelMessage("assistant", response.content, response.tool_calls))
                for call in response.tool_calls:
                    self.cancel.check()
                    self._deadline(started)
                    within_limit = self.budget.reserve_tool_call()
                    execution = runtime.executor.execute(
                        call,
                        company_id=caller.company_id,
                        user_id=caller.user_id,
                        evidence=self.evidence,
                        within_limit=within_limit,
                    )
                    ordinal += 1
                    self._flag(execution.safety_flags)
                    runtime.office.record_tool_call(
                        company_id=caller.company_id,
                        user_id=caller.user_id,
                        run_id=self.run_record.id,
                        ordinal=ordinal,
                        execution=execution,
                        request_id=caller.request_id,
                    )
                    messages.append(
                        ModelMessage(
                            "tool", execution.content, tool_call_id=call.id, tool_name=call.name
                        )
                    )
                continue
            final_text = response.content
            break
        else:
            raise AIBudgetExceededError("The model-step limit for this request has been reached.")

        if not final_text or not final_text.strip():
            raise ProviderBadResponseError()
        return self._complete(final_text)

    def _complete(self, final_text: str) -> RunFinish:
        parsed = parse_model_json(final_text)
        result = (
            validate_response(parsed, self.evidence)
            if parsed
            else unstructured_response(final_text)
        )
        response = result.response
        response["warnings"] = result.warnings
        cited = _cited_ids(response)
        evidence = [
            found.to_json() for found in (self.evidence.get(i) for i in cited) if found is not None
        ]
        proposals = extract_proposals(response, self.evidence)
        summary = response.get("summary") or "The assistant returned no summary."
        return self._finish(
            RunStatus.COMPLETED,
            warnings=result.warnings,
            text=summary,
            structured=response,
            evidence=evidence,
            proposals=proposals,
        )


def _cited_ids(response: dict[str, Any]) -> list[str]:
    seen: list[str] = []

    def add(ids: Any) -> None:
        for evidence_id in ids or []:
            if evidence_id not in seen:
                seen.append(evidence_id)

    for finding in response.get("findings", []):
        add(finding.get("evidence"))
        for figure in finding.get("figures", []):
            add([figure.get("evidence")])
    for section in ("recommendations", "missing_inputs", "drafts", "task_proposals"):
        for item in response.get(section, []):
            add(item.get("evidence"))
    return sorted(seen, key=lambda value: int(value[1:]) if value[1:].isdigit() else 0)
