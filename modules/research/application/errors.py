"""Research application errors (ticket #24).

Embedding failures happen off-request in the dispatcher, never in an HTTP
handler: the pipeline records them on the source row (failed, retryable)
via the generic ``PlatformError`` → failure path. They subclass
``PlatformError`` so the dispatcher's except-``PlatformError``-agnostic
machinery keeps working, and they are typed so operators can tell
configuration problems from provider outages.
"""

from modules.platform.domain.errors import PlatformError


class EmbeddingConfigurationError(PlatformError):
    """No embedding provider/model configured (or the model could not be
    constructed). The source lands failed; configure the environment and
    retry."""


class EmbeddingProviderError(PlatformError):
    """The configured provider failed mid-call (network, auth, bad
    dimensions). Transient cases clear on retry."""
