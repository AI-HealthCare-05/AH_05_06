import asyncio
import uuid
from pathlib import Path
from typing import Protocol

ALLOWED_MIME_TYPES: frozenset[str] = frozenset(
    {
        "image/jpeg",
        "image/png",
        "application/pdf",
    }
)

ALLOWED_EXTENSIONS_BY_MIME: dict[str, frozenset[str]] = {
    "image/jpeg": frozenset({".jpg", ".jpeg"}),
    "image/png": frozenset({".png"}),
    "application/pdf": frozenset({".pdf"}),
}

FILE_SIGNATURES_BY_MIME: dict[str, tuple[bytes, ...]] = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "application/pdf": (b"%PDF-",),
}

_MIME_TO_EXT: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "application/pdf": ".pdf",
}


class StorageBackend(Protocol):
    async def save(self, content: bytes, mime_type: str) -> str: ...
    async def delete(self, path: str) -> None: ...


class LocalFileStorage:
    def __init__(self, upload_dir: str) -> None:
        self._dir = Path(upload_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    async def save(self, content: bytes, mime_type: str) -> str:
        ext = _MIME_TO_EXT.get(mime_type, ".bin")
        path = self._dir / f"{uuid.uuid4().hex}{ext}"
        await asyncio.to_thread(path.write_bytes, content)
        return str(path)

    async def delete(self, path: str) -> None:
        await asyncio.to_thread(Path(path).unlink, True)
