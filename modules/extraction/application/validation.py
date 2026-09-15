"""Strict structured-output validation for extraction (spec #49).

The model's reply must be a single JSON object shaped like the schema
in prompting.EXTRACTION_SYSTEM_PROMPT. Validation is deliberately
total: anything unexpected — wrong types, unknown kinds, confidence
outside [0, 1], sentiment on a price — raises ExtractionValidationError.
The adapter retries once with a repair hint; a second failure is
surfaced as the typed error, never a partial silent result.
"""

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from modules.extraction.domain.entities import (
    EXTRACTION_KINDS,
    ExtractedItem,
    ExtractionResult,
)
from modules.extraction.domain.errors import ExtractionValidationError

_REVIEW_SENTIMENTS = ("positive", "neutral", "negative")
_MAX_EXCERPT_CHARS = 300
_MAX_ITEMS = 200

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


def _coerce_json_text(text: str) -> Any:
    """Accept a bare JSON object or a single ```json fence; reject prose,
    multiple objects, or anything json.loads cannot map."""
    stripped = text.strip()
    fenced = _JSON_FENCE_RE.match(stripped)
    if fenced:
        stripped = fenced.group(1).strip()
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ExtractionValidationError(
            f"model output is not valid JSON: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise ExtractionValidationError(
            "model output must be a single JSON object"
        )
    return payload


def _require_str(item: dict[str, Any], field: str, *, allow_empty: bool = False) -> str:
    value = item.get(field)
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ExtractionValidationError(
            f"item field {field!r} must be a non-empty string"
        )
    return value.strip()


def _optional_str(item: dict[str, Any], field: str) -> str | None:
    value = item.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ExtractionValidationError(f"item field {field!r} must be a string or null")
    value = value.strip()
    return value or None


def _parse_item(raw: Any) -> ExtractedItem:
    if not isinstance(raw, dict):
        raise ExtractionValidationError("each item must be a JSON object")

    kind = _require_str(raw, "kind")
    if kind not in EXTRACTION_KINDS:
        raise ExtractionValidationError(f"unknown item kind {kind!r}")

    claim = _require_str(raw, "claim")
    excerpt = _optional_str(raw, "excerpt")
    if excerpt is not None and len(excerpt) > _MAX_EXCERPT_CHARS:
        raise ExtractionValidationError(
            f"excerpt exceeds {_MAX_EXCERPT_CHARS} characters"
        )

    confidence_raw = raw.get("confidence")
    if isinstance(confidence_raw, bool):
        raise ExtractionValidationError("confidence must be a number in [0, 1]")
    try:
        confidence = Decimal(str(confidence_raw))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ExtractionValidationError(
            "confidence must be a number in [0, 1]"
        ) from exc
    if not Decimal(0) <= confidence <= Decimal(1):
        raise ExtractionValidationError("confidence must be within [0, 1]")

    price_amount: Decimal | None = None
    price_currency = _optional_str(raw, "price_currency")
    amount_raw = raw.get("price_amount")
    if amount_raw is not None:
        if kind != "price":
            raise ExtractionValidationError("price_amount only allowed for kind=price")
        if isinstance(amount_raw, bool) or not isinstance(amount_raw, (str, int, float)):
            raise ExtractionValidationError("price_amount must be a numeric string or number")
        try:
            price_amount = Decimal(str(amount_raw))
        except InvalidOperation as exc:
            raise ExtractionValidationError(
                "price_amount must be a numeric string or number"
            ) from exc
        if price_amount <= 0:
            raise ExtractionValidationError("price_amount must be positive")
    if kind == "price" and price_amount is None:
        raise ExtractionValidationError("kind=price requires price_amount")
    if price_currency is not None and kind != "price":
        raise ExtractionValidationError("price_currency only allowed for kind=price")

    sentiment = _optional_str(raw, "sentiment")
    if sentiment is not None:
        if kind != "review_topic":
            raise ExtractionValidationError("sentiment only allowed for kind=review_topic")
        if sentiment not in _REVIEW_SENTIMENTS:
            raise ExtractionValidationError(
                f"sentiment must be one of {_REVIEW_SENTIMENTS}"
            )

    return ExtractedItem(
        kind=kind,
        claim=claim,
        confidence=confidence,
        price_amount=price_amount,
        price_currency=price_currency,
        sentiment=sentiment,
        excerpt=excerpt,
    )


def parse_result_payload(text: str) -> ExtractionResult:
    """Validate one model reply into an ExtractionResult.

    Raises ExtractionValidationError on any deviation from the schema.
    Items with confidence below 0.3 are dropped (the system prompt asks
    the model to do this; we enforce it rather than trust it)."""
    payload = _coerce_json_text(text)
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise ExtractionValidationError("model output must contain an 'items' array")
    if len(raw_items) > _MAX_ITEMS:
        raise ExtractionValidationError(f"at most {_MAX_ITEMS} items allowed")

    items = [_parse_item(raw) for raw in raw_items]
    kept = tuple(item for item in items if item.confidence >= Decimal("0.3"))
    return ExtractionResult(items=kept)
