"""Typed extraction errors (spec #49).

Mirrors the embedder failure policy (ticket #24): unconfigured deploys
boot and fail visibly per call; provider failures wrap the cause;
malformed model output is a typed validation error — never a bare
exception, never a silent partial result.
"""


class ExtractionError(Exception):
    """Base for all extraction failures."""


class ExtractionConfigurationError(ExtractionError):
    """Provider/model unset or not constructible."""


class ExtractionProviderError(ExtractionError):
    """The provider call itself failed (network, auth, rate limit…)."""


class ExtractionValidationError(ExtractionError):
    """Model output did not match the extraction schema after retries."""
