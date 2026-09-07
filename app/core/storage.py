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
    async def exists(self, path: str) -> bool: ...


class LocalFileStorage:
    def __init__(self, upload_dir: str) -> None:
        self._configured_dir = Path(upload_dir)
        self._dir = self._configured_dir.resolve()
        self._dir.mkdir(parents=True, exist_ok=True)

    def _stored_path(self, path: str) -> Path:
        candidate = Path(path)
        if candidate.is_absolute():
            return candidate

        # 예전 행은 ``UPLOAD_DIR/파일명``을 상대 경로로 저장했고, 새 저장소는
        # 작업 디렉터리와 무관하게 절대 경로를 반환한다. 두 형식을 모두 저장
        # 루트 기준으로 해석해 Worker의 CWD가 달라도 같은 파일을 가리킨다.
        try:
            relative = candidate.relative_to(self._configured_dir)
        except ValueError:
            relative = candidate
        return self._dir / relative

    async def save(self, content: bytes, mime_type: str) -> str:
        ext = _MIME_TO_EXT.get(mime_type, ".bin")
        path = self._dir / f"{uuid.uuid4().hex}{ext}"
        await asyncio.to_thread(path.write_bytes, content)
        return str(path)

    async def delete(self, path: str) -> None:
        await asyncio.to_thread(self._stored_path(path).unlink, True)

    async def exists(self, path: str) -> bool:
        def _stat() -> bool:
            try:
                self._stored_path(path).stat()
            except FileNotFoundError:
                return False
            return True

        return await asyncio.to_thread(_stat)
