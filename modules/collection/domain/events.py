"""Collection outbox event types (spec #41, PDR-003).

Payloads are plain JSON dicts of string keys; every payload carries the
tenant scope (organization_id/project_id) so consumers never need to look
the job up to know which tenancy it belongs to.
"""

COLLECTION_JOB_REQUESTED = "CollectionJobRequested"
COLLECTION_SNAPSHOT_CREATED = "CollectionSnapshotCreated"
COLLECTION_DUE = "CollectionDue"
