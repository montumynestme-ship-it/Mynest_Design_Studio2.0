import io
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# 1x1 transparent PNG.
PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05"
    b"\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture
def destination() -> Iterator[tuple[str, str]]:
    """A throwaway project + floor; deleted (with its floor plans) after the test."""
    project = client.post(
        "/api/projects", json={"name": "__test_project__", "floor_count": 1}
    ).json()
    yield project["id"], project["floors"][0]["id"]
    client.delete(f"/api/projects/{project['id']}")


def test_create_and_delete_project() -> None:
    created = client.post("/api/projects", json={"name": "Test Project", "floor_count": 2})
    assert created.status_code == 201
    project = created.json()
    assert project["name"] == "Test Project"
    assert len(project["floors"]) == 2

    listing = client.get("/api/projects")
    assert any(p["id"] == project["id"] for p in listing.json())

    deleted = client.delete(f"/api/projects/{project['id']}")
    assert deleted.status_code == 200
    assert all(p["id"] != project["id"] for p in client.get("/api/projects").json())


def test_upload_list_get_delete_flow(destination: tuple[str, str]) -> None:
    project_id, floor_id = destination

    upload = client.post(
        "/api/floor-plans/upload",
        files={"file": ("living-room.png", io.BytesIO(PNG_BYTES), "image/png")},
        data={"project_id": project_id, "floor_id": floor_id},
    )
    assert upload.status_code == 201, upload.text
    body = upload.json()
    assert body["status"] == "uploaded"
    assert body["file_type"] == "png"
    assert body["original_filename"] == "living-room.png"
    assert body["project_id"] == project_id
    plan_id = body["id"]

    try:
        listing = client.get("/api/floor-plans", params={"project_id": project_id})
        assert listing.status_code == 200
        assert any(item["id"] == plan_id for item in listing.json())

        detail = client.get(f"/api/floor-plans/{plan_id}")
        assert detail.status_code == 200
        assert detail.json()["id"] == plan_id

        raw = client.get(f"/api/floor-plans/{plan_id}/file")
        assert raw.status_code == 200
        assert raw.headers["content-type"].startswith("image/png")
    finally:
        deleted = client.delete(f"/api/floor-plans/{plan_id}")
        assert deleted.status_code == 200

    assert client.get(f"/api/floor-plans/{plan_id}").status_code == 404


def test_unsupported_extension_rejected(destination: tuple[str, str]) -> None:
    project_id, floor_id = destination
    response = client.post(
        "/api/floor-plans/upload",
        files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
        data={"project_id": project_id, "floor_id": floor_id},
    )
    assert response.status_code == 415


def test_unknown_project_rejected() -> None:
    response = client.post(
        "/api/floor-plans/upload",
        files={"file": ("living-room.png", io.BytesIO(PNG_BYTES), "image/png")},
        data={"project_id": "not-a-real-project", "floor_id": "nope"},
    )
    assert response.status_code == 404
