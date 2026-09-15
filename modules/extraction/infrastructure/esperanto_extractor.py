"""Esperanto-backed LLM extractor (spec #49, ticket #49): the reference
Extractor port implementation. Configuration arrives from the
composition root (Settings → env); nothing here reads the environment
(plan §14.2).

Failure policy (mirrors the ticket #24 embedder):
- Unconfigured provider/model: ``ExtractionConfigurationError`` raised
  at extract time — the run lands failed and retryable, never a
  startup crash and never a bare exception.
- Provider call failures (network, auth, …): ``ExtractionProviderError``
  wrapping the cause.
- Malformed model output: one retry with a repair hint, then a typed
  ``ExtractionValidationError`` — never a silent partial result.
The model is constructed lazily on first use so an unconfigured deploy
can still boot (and enqueue extraction work that fails visibly).

A prebuilt model object can be injected (constructor arg) — the
composition root doesn't need it, but tests do: they fake the language
model without any network or provider configuration.
"""

from typing import Any

from esperanto import AIFactory

from modules.extraction.application.prompting import (
    REPAIR_HINT,
    build_extraction_messages,
)
from modules.extraction.application.validation import parse_result_payload
from modules.extraction.domain.entities import ExtractionResult
from modules.extraction.domain.errors import (
    ExtractionConfigurationError,
    ExtractionProviderError,
    ExtractionValidationError,
)

MAX_OUTPUT_TOKENS = 2000


class EsperantoExtractor:
    """Settings-driven extractor: provider name, model name, optional
    API key (when empty, the provider's standard env var applies — the
    same mechanism the env config uses)."""

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
        assert model is not None  # set in extract() before first use
        completion = await model.achat_complete(messages=messages)
        content = completion.choices[0].message.content
        if not isinstance(content, str) or not content.strip():
            raise ExtractionProviderError("provider returned an empty completion")
        return content

    async def extract(
        self, *, source_text: str, source_url: str | None = None
    ) -> ExtractionResult:
        if self._model is None:
            if not self._provider or not self._model_name:
                raise ExtractionConfigurationError(
                    "extraction provider/model not configured: set"
                    " OPEN_INTEL_EXTRACTION_PROVIDER and"
                    " OPEN_INTEL_EXTRACTION_MODEL"
                )
            try:
                self._model = self._build_model()
            except Exception as exc:
                raise ExtractionConfigurationError(
                    f"extraction model could not be constructed: {exc}"
                ) from exc

        messages = build_extraction_messages(
            source_text=source_text, source_url=source_url
        )
        try:
            text = await self._complete(messages)
        except Exception as exc:
            if isinstance(exc, ExtractionProviderError):
                raise
            raise ExtractionProviderError(f"extraction provider failed: {exc}") from exc

        try:
            return parse_result_payload(text)
        except ExtractionValidationError:
            pass  # one repair retry before giving up

        try:
            repair = await self._complete(
                messages
                + [
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": REPAIR_HINT},
                ]
            )
        except Exception as exc:
            raise ExtractionProviderError(
                f"extraction provider failed during repair retry: {exc}"
            ) from exc
        return parse_result_payload(repair)
