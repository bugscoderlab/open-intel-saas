"""Esperanto-backed tool router (ticket #60): the reference ToolRouter
port implementation. Mirrors the #49 adapter policy: Settings-driven,
lazily constructed, typed configuration/provider errors, injectable
model for tests.

Plan discipline: the model is asked for a structured JSON plan; the
reply is strictly parsed and validated against the allowlist (tools +
argument schemas). A malformed or disallowed plan gets ONE repair
retry; a second failure yields an empty plan — the orchestration then
reports 'analysis unavailable' instead of crashing (spec exit
condition).
"""

from typing import Any

from esperanto import AIFactory

from modules.intelligence_chat.application.plan_validation import (
    parse_plan_payload,
    validate_plan_against_allowlist,
)
from modules.intelligence_chat.application.router_prompting import (
    MAX_PLAN_STEPS,
    ROUTER_REPAIR_HINT,
    build_router_messages,
    describe_tools,
)
from modules.intelligence_chat.domain.entities import ToolPlan, ToolSpec
from modules.intelligence_chat.domain.errors import (
    ChatConfigurationError,
    ChatProviderError,
    PlanValidationError,
)
from modules.intelligence_chat.domain.ports import ToolRouter

MAX_OUTPUT_TOKENS = 1000


class EsperantoToolRouter(ToolRouter):
    """Settings-driven router: provider name, model name, optional API
    key (when empty, the provider's standard env var applies)."""

    def __init__(
        self,
        *,
        provider: str,
        model_name: str,
        api_key: str | None = None,
        model: Any | None = None,
    ) -> None:
        self._provider = provider.strip()
        self._model_name = model_name.strip()
        self._api_key = api_key
        self._model = model  # injected in tests; lazily built otherwise

    def _build_model(self) -> Any:
        config: dict = {}
        if self._api_key:
            config["api_key"] = self._api_key
        return AIFactory.create_language(
            provider=self._provider,
            model_name=self._model_name,
            config={"max_tokens": MAX_OUTPUT_TOKENS, **config},
        )

    async def _complete(self, messages: list[dict[str, str]]) -> str:
        model = self._model
        assert model is not None
        completion = await model.achat_complete(messages=messages)
        content = completion.choices[0].message.content
        if not isinstance(content, str) or not content.strip():
            raise ChatProviderError("provider returned an empty completion")
        return content

    async def plan(
        self, *, question: str, allowlist: tuple[ToolSpec, ...]
    ) -> ToolPlan:
        if self._model is None:
            if not self._provider or not self._model_name:
                raise ChatConfigurationError(
                    "chat provider/model not configured: set"
                    " OPEN_INTEL_CHAT_PROVIDER and OPEN_INTEL_CHAT_MODEL"
                )
            try:
                self._model = self._build_model()
            except Exception as exc:
                raise ChatConfigurationError(
                    f"chat model could not be constructed: {exc}"
                ) from exc

        messages = build_router_messages(
            question=question,
            tools_description=describe_tools(allowlist),
            max_steps=MAX_PLAN_STEPS,
        )
        try:
            text = await self._complete(messages)
        except Exception as exc:
            if isinstance(exc, ChatProviderError):
                raise
            raise ChatProviderError(f"chat provider failed: {exc}") from exc

        try:
            plan = parse_plan_payload(text)
            return validate_plan_against_allowlist(plan, allowlist)
        except PlanValidationError:
            pass  # one repair retry before dropping to an empty plan

        try:
            repair = await self._complete(
                messages
                + [
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": ROUTER_REPAIR_HINT},
                ]
            )
        except Exception as exc:
            raise ChatProviderError(
                f"chat provider failed during plan repair: {exc}"
            ) from exc
        try:
            plan = parse_plan_payload(repair)
            return validate_plan_against_allowlist(plan, allowlist)
        except PlanValidationError:
            return ToolPlan(steps=())
