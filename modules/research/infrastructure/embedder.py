"""Esperanto-backed embedder (ticket #24, spec #21): the provider library
the spec prescribes, DB-agnostic and portable. Configuration arrives
from the composition root (Settings → env); nothing here reads the
environment (plan §14.2).

Failure policy (per ticket acceptance):
- Unconfigured provider/model: ``EmbeddingConfigurationError`` raised at
  embed time — the source lands failed and retryable, never a startup
  crash and never a bare exception.
- Provider call failures (network, auth, …) and malformed results:
  ``EmbeddingProviderError`` wrapping the cause.
The model is constructed lazily on first use so an unconfigured deploy
can still boot and ingest (processing fails visibly per source).
"""

from esperanto import AIFactory
from esperanto.providers.embedding.base import EmbeddingModel

from modules.research.application.errors import (
    EmbeddingConfigurationError,
    EmbeddingProviderError,
)


class EsperantoEmbedder:
    """Settings-driven embedder: provider name, model name, optional API
    key (when empty, the provider's standard env var applies — the same
    mechanism the env config uses)."""

    def __init__(
        self,
        *,
        provider: str,
        model_name: str,
        api_key: str | None = None,
    ) -> None:
        self._provider = provider.strip()
        self._model_name = model_name.strip()
        self._api_key = api_key
        self._model: EmbeddingModel | None = None

    def _build_model(self) -> EmbeddingModel:
        config: dict = {}
        if self._api_key:
            config["api_key"] = self._api_key
        return AIFactory.create_embedding(
            provider=self._provider, model_name=self._model_name, config=config
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not self._provider or not self._model_name:
            raise EmbeddingConfigurationError(
                "embedding provider/model not configured: set"
                " OPEN_INTEL_EMBEDDING_PROVIDER and OPEN_INTEL_EMBEDDING_MODEL"
            )
        if self._model is None:
            try:
                self._model = self._build_model()
            except Exception as exc:
                raise EmbeddingConfigurationError(
                    f"embedding model could not be constructed: {exc}"
                ) from exc
        try:
            return await self._model.aembed(texts)
        except Exception as exc:
            raise EmbeddingProviderError(f"embedding provider failed: {exc}") from exc
