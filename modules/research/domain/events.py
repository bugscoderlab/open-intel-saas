"""Research module outbox event types (spec #21, plan §14.5).

Event payloads are plain JSON dicts of string keys; every payload carries
the tenant scope (organization_id/project_id) so consumers never need to
look the source up to know which tenancy it belongs to.
"""

SOURCE_SUBMITTED = "SourceSubmitted"
SOURCE_PROCESSING_COMPLETED = "SourceProcessingCompleted"
