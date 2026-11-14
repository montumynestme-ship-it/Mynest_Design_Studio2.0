from fastapi import APIRouter, HTTPException

from app.schemas.floor_plan import ProjectCreate, ProjectResponse
from app.services import floor_plan_service, project_service

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=list[ProjectResponse])
def list_projects() -> list[ProjectResponse]:
    """Catalog of user-created projects, used as upload destinations."""
    return project_service.list_projects()


@router.post("", response_model=ProjectResponse, status_code=201)
def create_project(payload: ProjectCreate) -> ProjectResponse:
    return project_service.create_project(payload)


@router.delete("/{project_id}")
def delete_project(project_id: str) -> dict[str, str | int]:
    if project_service.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    # Remove floor-plan files (and their rows) before deleting the project.
    removed = floor_plan_service.delete_floor_plans_for_project(project_id)
    project_service.delete_project(project_id)
    return {"id": project_id, "status": "deleted", "floor_plans_removed": removed}
