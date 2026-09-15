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
    RUN_FAILED,
    RUN_PENDING,
    RUN_STATES,
    RUN_SUCCEEDED,
    ExtractedItem,
    ExtractionResult,
    ExtractionRun,
)
from modules.extraction.domain.errors import (
    ExtractionConfigurationError,
    ExtractionError,
    ExtractionProviderError,
    ExtractionValidationError,
)
from modules.extraction.domain.ports import (
    Extractor,
    ObservationSink,
    ProposedFact,
    SnapshotContent,
    SnapshotSource,
)

__all__ = [
    "EXTRACTION_KINDS",
    "EXTRACTION_VERSION",
    "KIND_POSITIONING",
    "KIND_PRICE",
    "KIND_PROMOTION",
    "KIND_REVIEW_TOPIC",
    "KIND_SERVICE",
    "RUN_FAILED",
    "RUN_PENDING",
    "RUN_STATES",
    "RUN_SUCCEEDED",
    "ExtractedItem",
    "ExtractionResult",
    "ExtractionRun",
    "ExtractionConfigurationError",
    "ExtractionError",
    "ExtractionProviderError",
    "ExtractionValidationError",
    "Extractor",
    "ObservationSink",
    "ProposedFact",
    "SnapshotContent",
    "SnapshotSource",
]
