"""Text hygiene for user- and source-supplied content (spec #31).

Plan §16 Phase 3 exit requirement: server-side field allowlists and
output sanitization. The allowlist half lives at the API boundary
(Pydantic response models expose exactly the allowlisted fields); this
module is the input half — anything that will be rendered back to a
user later is stripped of control characters before it is persisted.
Pure function, no dependencies (plan §14.2 domain purity).
"""

MAX_TEXT_LENGTH = 10_000

# C0 controls that must never survive into stored content. Tab, LF and
# CR are the printable whitespace exceptions.
_ALLOWED_CONTROLS = {"\t", "\n", "\r"}


def sanitize_text(value: str, *, max_length: int = MAX_TEXT_LENGTH) -> str:
    """Strip C0/C1 control characters (except tab/newline/CR) and cap
    the length. Idempotent and total — every text field passes through
    here before persistence, user- and source-supplied alike."""
    cleaned = "".join(
        ch for ch in value if ord(ch) >= 0x20 or ch in _ALLOWED_CONTROLS
    )
    return cleaned[:max_length]


def sanitize_optional(value: str | None, *, max_length: int = MAX_TEXT_LENGTH) -> str | None:
    """Nullable wrapper for nullable text fields."""
    if value is None:
        return None
    return sanitize_text(value, max_length=max_length)
