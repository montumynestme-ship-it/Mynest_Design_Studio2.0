from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import floor_plans, generations, invoices, projects
from app.db.base import init_db
from app.storage.file_storage import ensure_storage_ready


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    ensure_storage_ready()
    init_db()
    yield


app = FastAPI(title="MyNest Design Studio API", lifespan=lifespan)

# Allow the Vite dev server to call the API from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health_check() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}


app.include_router(projects.router)
app.include_router(floor_plans.router)
app.include_router(generations.router)
app.include_router(invoices.router)
