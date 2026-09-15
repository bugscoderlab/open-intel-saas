"""Domain layer: extraction value types, typed errors, and ports.

Pure domain — no framework or provider imports (lint-imports contract).
"""

from modules.extraction.domain.entities import (
    EXTRACTION_KINDS,
    EXTRACTION_VERSION,
    KIND_POSITIONING,
    KIND_PRICE,
    KIND_PROMOTION,
    KIND_REVIEW_TOPIC,
    KIND_SERVICE,
    ExtractedItem,
    ExtractionResult,
)
from modules.extraction.domain.errors import (
    ExtractionConfigurationError,
    ExtractionError,
    ExtractionProviderError,
    ExtractionValidationError,
)
from modules.extraction.domain.ports import Extractor

__all__ = [
    "EXTRACTION_KINDS",
    "EXTRACTION_VERSION",
    "KIND_POSITIONING",
    "KIND_PRICE",
    "KIND_PROMOTION",
    "KIND_REVIEW_TOPIC",
    "KIND_SERVICE",
    "ExtractedItem",
    "ExtractionResult",
    "ExtractionConfigurationError",
    "ExtractionError",
    "ExtractionProviderError",
    "ExtractionValidationError",
    "Extractor",
]
