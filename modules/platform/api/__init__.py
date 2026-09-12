"""HTTP API layer of the platform module.

Routers and the FastAPI app factory. This layer may depend on
``application`` and ``domain`` only — never ``infrastructure``
(enforced by import-linter); composition happens in the root
``serve.py`` entrypoint.
"""

from modules.platform.api.app import create_app

__all__ = ["create_app"]
