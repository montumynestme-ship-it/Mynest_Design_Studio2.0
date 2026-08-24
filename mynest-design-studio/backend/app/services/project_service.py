import uuid

from app.db.base import session_scope
from app.db.models import Floor as FloorModel
from app.db.models import Project as ProjectModel
from app.schemas.floor_plan import FloorResponse, ProjectCreate, ProjectResponse

_FLOOR_NAMES = [
    "Ground Floor",
    "First Floor",
    "Second Floor",
    "Third Floor",
    "Fourth Floor",
]


def _as_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return None


def _to_response(project: ProjectModel) -> ProjectResponse:
    floors = sorted(project.floors, key=lambda f: f.order_index)
    return ProjectResponse(
        id=str(project.id),
        name=project.name,
        client_name=project.client_name,
        property_type=project.property_type,
        floors=[FloorResponse(id=str(f.id), name=f.name) for f in floors],
    )


def list_projects() -> list[ProjectResponse]:
    with session_scope() as db:
        rows = db.query(ProjectModel).order_by(ProjectModel.created_at).all()
        return [_to_response(p) for p in rows]


def get_project(project_id: str) -> ProjectResponse | None:
    pid = _as_uuid(project_id)
    if pid is None:
        return None
    with session_scope() as db:
        project = db.get(ProjectModel, pid)
        return _to_response(project) if project else None


def get_floor(project: ProjectResponse, floor_id: str) -> FloorResponse | None:
    return next((f for f in project.floors if f.id == floor_id), None)


def resolve_names(project_id: str, floor_id: str) -> tuple[str | None, str | None]:
    project = get_project(project_id)
    if project is None:
        return None, None
    floor = get_floor(project, floor_id)
    return project.name, (floor.name if floor else None)


def create_project(payload: ProjectCreate) -> ProjectResponse:
    count = max(1, min(payload.floor_count, len(_FLOOR_NAMES)))
    with session_scope() as db:
        project = ProjectModel(
            name=payload.name.strip() or "Untitled Project",
            client_name=payload.client_name,
            property_type=payload.property_type,
        )
        for i in range(count):
            project.floors.append(FloorModel(name=_FLOOR_NAMES[i], order_index=i))
        db.add(project)
        db.flush()
        return _to_response(project)


def delete_project(project_id: str) -> bool:
    pid = _as_uuid(project_id)
    if pid is None:
        return False
    with session_scope() as db:
        project = db.get(ProjectModel, pid)
        if project is None:
            return False
        db.delete(project)
        return True
