"""승인 의료지식 원문용 private MinIO 경계 — KEY-276."""

from __future__ import annotations

import asyncio
from io import BytesIO
from typing import Protocol


class PrivateObjectStore(Protocol):
    async def put(self, object_key: str, payload: bytes, content_type: str) -> None: ...

    async def get(self, object_key: str) -> bytes: ...


def validate_private_object_key(object_key: str) -> str:
    if not object_key or object_key.startswith("/") or ".." in object_key.split("/"):
        raise ValueError("INVALID_PRIVATE_OBJECT_KEY")
    if "://" in object_key:
        raise ValueError("PUBLIC_OBJECT_URL_FORBIDDEN")
    return object_key


class MinioPrivateObjectStore:
    """URL을 발급하지 않고 object key만 받는 좁은 MinIO 어댑터.

    `secure`은 endpoint scheme에서만 정하며, 자격증명은 설정/secret에서 주입한다.
    응답이나 예외에 원문과 자격증명을 포함하지 않는다.
    """

    def __init__(
        self,
        *,
        endpoint: str,
        bucket: str,
        access_key: str,
        secret_key: str,
    ) -> None:
        try:
            from minio import Minio
        except ImportError as exc:  # pragma: no cover - 이미지 import 검사에서 검증
            raise RuntimeError("MINIO_CLIENT_NOT_INSTALLED") from exc

        normalized = endpoint.removeprefix("http://").removeprefix("https://").rstrip("/")
        self._client = Minio(
            normalized,
            access_key=access_key,
            secret_key=secret_key,
            secure=endpoint.startswith("https://"),
        )
        self._bucket = bucket

    async def put(self, object_key: str, payload: bytes, content_type: str) -> None:
        key = validate_private_object_key(object_key)

        def _put() -> None:
            self._client.put_object(
                self._bucket,
                key,
                BytesIO(payload),
                length=len(payload),
                content_type=content_type,
            )

        try:
            await asyncio.to_thread(_put)
        except Exception as exc:
            raise RuntimeError("PRIVATE_OBJECT_PUT_FAILED") from exc

    async def get(self, object_key: str) -> bytes:
        key = validate_private_object_key(object_key)

        def _get() -> bytes:
            response = self._client.get_object(self._bucket, key)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()

        try:
            return await asyncio.to_thread(_get)
        except Exception as exc:
            raise RuntimeError("PRIVATE_OBJECT_GET_FAILED") from exc


class InMemoryPrivateObjectStore:
    """네트워크 없는 계약 테스트용. URL 공개 기능은 의도적으로 없다."""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}

    async def put(self, object_key: str, payload: bytes, content_type: str) -> None:
        self.objects[validate_private_object_key(object_key)] = (bytes(payload), content_type)

    async def get(self, object_key: str) -> bytes:
        try:
            return self.objects[validate_private_object_key(object_key)][0]
        except KeyError as exc:
            raise RuntimeError("PRIVATE_OBJECT_NOT_FOUND") from exc


def build_configured_knowledge_store() -> MinioPrivateObjectStore:
    """전역 설정에서 자격증명을 꺼내되 값 자체는 노출하지 않는다."""

    from app.core import config

    access_key = config.MINIO_ROOT_USER.get_secret_value()
    secret_key = config.MINIO_ROOT_PASSWORD.get_secret_value()
    if not access_key or not secret_key:
        raise RuntimeError("KNOWLEDGE_MINIO_NOT_CONFIGURED")
    return MinioPrivateObjectStore(
        endpoint=config.KNOWLEDGE_MINIO_ENDPOINT,
        bucket=config.KNOWLEDGE_MINIO_BUCKET,
        access_key=access_key,
        secret_key=secret_key,
    )
