import contextlib
from pathlib import PurePath
from uuid import uuid4

from fastapi import UploadFile, status
from tortoise.transactions import in_transaction

from app.core.api_errors import ApiError
from app.core.storage import (
    ALLOWED_EXTENSIONS_BY_MIME,
    ALLOWED_MIME_TYPES,
    FILE_SIGNATURES_BY_MIME,
    StorageBackend,
)
from app.documents.schemas import DocumentUploadResponse
from app.models.documents import MedicalDocument
from app.models.ocr import OcrDocumentType, OcrJob, OcrJobDocument, OcrJobStatus
from app.models.visits import Visit


class DocumentUploadService:
    def __init__(self, storage: StorageBackend, max_upload_bytes: int) -> None:
        self._storage = storage
        self._max_bytes = max_upload_bytes

    async def upload(
        self,
        *,
        visit_id: int,
        files: list[UploadFile],
        document_type: OcrDocumentType | None,
        hospital_id: int,
        staff_id: int,
    ) -> DocumentUploadResponse:
        validated = await self._read_and_validate(files)
        await self._verify_visit_access(visit_id=visit_id, hospital_id=hospital_id)
        effective_type = document_type or OcrDocumentType.EMR

        saved_paths: list[str] = []
        try:
            for content, mime in validated:
                path = await self._storage.save(content, mime)
                saved_paths.append(path)
        except Exception:
            for path in saved_paths:
                with contextlib.suppress(Exception):
                    await self._storage.delete(path)
            raise

        try:
            document_ids, ocr_job_id = await self._persist(
                visit_id=visit_id,
                validated=validated,
                saved_paths=saved_paths,
                document_type=effective_type,
                hospital_id=hospital_id,
                staff_id=staff_id,
            )
        except Exception:
            for path in saved_paths:
                with contextlib.suppress(Exception):
                    await self._storage.delete(path)
            raise

        return DocumentUploadResponse(
            document_ids=document_ids,
            ocr_job_id=ocr_job_id,
            status=OcrJobStatus.PROCESSING,
        )

    async def _persist(
        self,
        *,
        visit_id: int,
        validated: list[tuple[bytes, str]],
        saved_paths: list[str],
        document_type: OcrDocumentType,
        hospital_id: int,
        staff_id: int,
    ) -> tuple[list[int], str]:
        async with in_transaction() as conn:
            visit = (
                await Visit.filter(visit_id=visit_id, hospital_id=hospital_id)
                .using_db(conn)
                .select_for_update()
                .first()
            )
            if visit is None:
                raise ApiError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "진료 건을 찾을 수 없습니다.")

            documents: list[MedicalDocument] = []
            for (content, mime), path in zip(validated, saved_paths, strict=True):
                doc = await MedicalDocument.create(
                    hospital_id=hospital_id,
                    visit=visit,
                    document_type=document_type,
                    file_path=path,
                    file_size=len(content),
                    mime_type=mime,
                    uploaded_by=staff_id,
                    using_db=conn,
                )
                documents.append(doc)

            ocr_job = await OcrJob.create(
                ocr_job_id=f"ocr_{uuid4().hex}",
                hospital_id=hospital_id,
                visit=visit,
                requested_by=staff_id,
                using_db=conn,
            )
            for doc in documents:
                await OcrJobDocument.create(
                    ocr_job=ocr_job,
                    document_id=doc.document_id,
                    document_type=document_type,
                    using_db=conn,
                )

        return [doc.document_id for doc in documents], ocr_job.ocr_job_id

    async def _verify_visit_access(self, *, visit_id: int, hospital_id: int) -> None:
        exists = await Visit.filter(visit_id=visit_id, hospital_id=hospital_id).exists()
        if not exists:
            raise ApiError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "진료 건을 찾을 수 없습니다.")

    async def _read_and_validate(self, files: list[UploadFile]) -> list[tuple[bytes, str]]:
        if not files:
            raise ApiError(status.HTTP_400_BAD_REQUEST, "INVALID_REQUEST", "파일을 하나 이상 업로드해 주세요.")

        result: list[tuple[bytes, str]] = []
        for upload in files:
            mime = upload.content_type or ""
            filename = upload.filename or ""
            suffix = PurePath(filename).suffix.lower()
            has_path_component = "/" in filename or "\\" in filename or "\x00" in filename
            if (
                mime not in ALLOWED_MIME_TYPES
                or suffix not in ALLOWED_EXTENSIONS_BY_MIME.get(mime, frozenset())
                or has_path_component
            ):
                raise ApiError(
                    status.HTTP_400_BAD_REQUEST,
                    "INVALID_FILE_TYPE",
                    "지원하지 않는 파일 형식입니다. (허용: JPEG, PNG, PDF)",
                )
            # 제한을 넘겼는지만 판단할 만큼만 읽어, 초대형 요청이 애플리케이션
            # 메모리를 파일 크기만큼 점유하지 못하게 한다.
            content = await upload.read(self._max_bytes + 1)
            if len(content) == 0:
                raise ApiError(status.HTTP_400_BAD_REQUEST, "INVALID_REQUEST", "빈 파일은 업로드할 수 없습니다.")
            if len(content) > self._max_bytes:
                raise ApiError(
                    status.HTTP_413_CONTENT_TOO_LARGE,
                    "FILE_TOO_LARGE",
                    f"파일 크기가 제한을 초과합니다. (최대 {self._max_bytes // 1024 // 1024}MB)",
                )
            signatures = FILE_SIGNATURES_BY_MIME[mime]
            if not any(content.startswith(signature) for signature in signatures):
                raise ApiError(
                    status.HTTP_400_BAD_REQUEST,
                    "INVALID_FILE_TYPE",
                    "파일 내용과 형식이 일치하지 않습니다.",
                )
            result.append((content, mime))
        return result
