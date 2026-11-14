from app.schemas.floor_plan import ProjectResponse

# The project catalog is empty by default — projects are created by the user
# via project_service (POST /api/projects). No demo/seed projects are shipped.
PROJECTS: list[ProjectResponse] = []
