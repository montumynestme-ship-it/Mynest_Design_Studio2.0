from datetime import datetime

from pydantic import BaseModel


class FloorPlanRecord(BaseModel):
    """Persisted metadata for an uploaded floor plan.

    This is the storage-layer model. It is serialized to a `metadata.json`
    file next to the stored upload. The structure is intentionally simple so
    it can later be swapped for a PostgreSQL-backed repository without changing
    the service or API layers.
    """

    id: str
    project_id: str
    floor_id: str
    original_filename: str
    stored_filename: str
    file_path: str  # relative to BACKEND_DIR — never exposed to clients
    file_type: str
    file_size: int
    status: str = "uploaded"
    created_at: datetime
    updated_at: datetime
