"""Local filesystem storage for uploaded floor-plan files.

File bytes live on local disk; metadata lives in PostgreSQL (floor_plans table).

Layout: storage/floor_plans/{project|unassigned}/{floor|unassigned}/{file_id}/original.<ext>

Security:
- The stored filename is always server-generated (UUID dir + ``original.<ext>``).
- The client-supplied filename is sanitized and kept only as metadata.
- Every resolved path is verified to stay within FLOOR_PLANS_DIR (no traversal).
"""

import re
import shutil
from pathlib import Path

from fastapi import UploadFile

from app.core.config import BACKEND_DIR, FLOOR_PLANS_DIR, GENERATIONS_DIR, MAX_FILE_SIZE

_CHUNK_SIZE = 1024 * 1024  # 1 MB


class FileTooLargeError(Exception):
    """Raised when an upload exceeds MAX_FILE_SIZE while streaming to disk."""


def sanitize_filename(filename: str) -> str:
    """Reduce a client filename to a safe basename (metadata display only)."""
    base = filename.replace("\\", "/").split("/")[-1].strip()
    base = re.sub(r"[^A-Za-z0-9._ -]", "_", base)
    base = base.lstrip(".") or "file"
    return base[:255]


def _seg(value: str) -> str:
    """Path segment for a project/floor id; empty ids go under 'unassigned'."""
    return value or "unassigned"


def _ensure_within_storage(path: Path) -> Path:
    resolved = path.resolve()
    root = FLOOR_PLANS_DIR.resolve()
    if root != resolved and root not in resolved.parents:
        raise ValueError("Resolved path escapes the storage root.")
    return resolved


def ensure_storage_ready() -> None:
    FLOOR_PLANS_DIR.mkdir(parents=True, exist_ok=True)
    GENERATIONS_DIR.mkdir(parents=True, exist_ok=True)


def save_generation_image(generation_id: str, index: int, data: bytes) -> None:
    gen_dir = GENERATIONS_DIR / generation_id
    gen_dir.mkdir(parents=True, exist_ok=True)
    (gen_dir / f"{index}.png").write_bytes(data)


def generation_image_path(generation_id: str, index: int) -> Path | None:
    path = GENERATIONS_DIR / generation_id / f"{index}.png"
    return path if path.is_file() else None


def delete_generation(generation_id: str) -> None:
    shutil.rmtree(GENERATIONS_DIR / generation_id, ignore_errors=True)


async def save_upload_stream(
    upload: UploadFile,
    project_id: str,
    floor_id: str,
    file_id: str,
    stored_filename: str,
) -> tuple[Path, int]:
    """Stream an upload to disk, enforcing the size limit. Returns (path, size)."""
    dest_dir = _ensure_within_storage(FLOOR_PLANS_DIR / _seg(project_id) / _seg(floor_id) / file_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / stored_filename

    size = 0
    await upload.seek(0)
    try:
        with dest.open("wb") as out:
            while True:
                chunk = await upload.read(_CHUNK_SIZE)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_FILE_SIZE:
                    raise FileTooLargeError()
                out.write(chunk)
    except FileTooLargeError:
        shutil.rmtree(dest_dir, ignore_errors=True)
        raise

    return dest, size


def abs_path(rel_path: str) -> Path | None:
    """Absolute path for a stored file (rel_path is relative to BACKEND_DIR)."""
    path = _ensure_within_storage((BACKEND_DIR / rel_path).resolve())
    return path if path.is_file() else None


def delete_file(rel_path: str) -> None:
    """Remove a stored file's {file_id} directory and prune empty parents."""
    path = (BACKEND_DIR / rel_path).resolve()
    try:
        _ensure_within_storage(path)
    except ValueError:
        return
    record_dir = path.parent
    shutil.rmtree(record_dir, ignore_errors=True)
    for parent in (record_dir.parent, record_dir.parent.parent):
        try:
            if parent.resolve() != FLOOR_PLANS_DIR.resolve() and not any(parent.iterdir()):
                parent.rmdir()
        except OSError:
            break
