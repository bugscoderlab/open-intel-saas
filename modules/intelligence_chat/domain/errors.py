"""Typed intelligence-chat errors (spec #58 assumption 2).

Mirrors the #49 failure policy: unconfigured provider → typed
configuration error at call time; provider failures wrap the cause;
malformed router plans and tool arguments are validation errors the
orchestration converts into unavailable notes — they never crash the
conversation.
"""


class ChatError(Exception):
    """Base for chat failures."""


class ChatConfigurationError(ChatError):
    """Chat provider/model unset or not constructible."""


class ChatProviderError(ChatError):
    """The provider call itself failed."""


class PlanValidationError(ChatError):
    """The router produced a malformed plan or named a disallowed tool."""


class ToolArgumentError(ChatError):
    """Tool arguments failed schema validation."""
