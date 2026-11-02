"""Where file bytes live. Local disk under settings.upload_dir for now (a
Docker volume in deployment); the storage key is generated here, so a user's
filename never becomes a path."""

import hashlib
import uuid
from pathlib import Path

from app.core.config import get_settings
from app.core.errors import NotFound


def _root() -> Path:
    root = Path(get_settings().upload_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def save_bytes(data: bytes) -> tuple[str, str]:
    """Write bytes and return (storage_key, sha256)."""
    key = f"{uuid.uuid4().hex[:2]}/{uuid.uuid4().hex}"
    path = _root() / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return key, hashlib.sha256(data).hexdigest()


def read_bytes(storage_key: str) -> bytes:
    root = _root()
    path = (root / storage_key).resolve()
    if root not in path.parents or not path.is_file():
        raise NotFound("file content not found")
    return path.read_bytes()


def remove(storage_key: str) -> None:
    root = _root()
    path = (root / storage_key).resolve()
    if root in path.parents and path.is_file():
        path.unlink()
