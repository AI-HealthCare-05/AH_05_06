from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.error_handlers import register_error_handlers
from app.models.ocr import OcrDocumentType, OcrJobStatus
from app.models.staffs import Staff
from app.ocr.api import get_ocr_service, ocr_router
from app.ocr.errors import OcrApiError
from app.ocr.schemas import (
    OcrDocumentResponse,
    OcrFieldResponse,
    OcrJobResponse,
    OcrResultResponse,
    UpdateOcrFieldRequest,
)
from app.ocr.security import OcrActor, get_ocr_actor

NOW = datetime(2026, 8, 19, 8, 0, tzinfo=UTC)
STAFF = OcrActor(staff_id=17, hospital_id=3, roles=frozenset({"staff"}))


class FakeOcrService:
    def __init__(self) -> None:
        self.updated: tuple[int, UpdateOcrFieldRequest, OcrActor] | None = None

    async def start(
        self, document_id: int, visit_id: int, document_type: OcrDocumentType, actor: OcrActor
    ) -> OcrJobResponse:
        assert (document_id, visit_id, document_type, actor.hospital_id) == (801, 501, OcrDocumentType.EMR, 3)
        return OcrJobResponse(
            ocr_job_id="ocr_synthetic_501",
            status=OcrJobStatus.PROCESSING,
            progress=0,
            started_at=None,
        )

    async def status(self, ocr_job_id: str, actor: OcrActor) -> OcrJobResponse:
        if ocr_job_id == "ocr_other_hospital":
            raise OcrApiError(404, "NOT_FOUND", "OCR 리소스를 찾을 수 없습니다.")
        return OcrJobResponse(
            ocr_job_id=ocr_job_id,
            status=OcrJobStatus.COMPLETED,
            progress=100,
            started_at=NOW,
            completed_at=NOW,
        )

    @staticmethod
    def field() -> OcrFieldResponse:
        return OcrFieldResponse(
            ocr_field_id=91,
            field_type="DIAGNOSIS",
            extracted_value="합성 추출값",
            corrected_value=None,
            value="합성 추출값",
            confidence=0.83,
            version=1,
            is_confirmed=False,
        )

    async def result(self, ocr_job_id: str, actor: OcrActor) -> OcrResultResponse:
        return OcrResultResponse(
            ocr_result_id=51,
            ocr_job_id=ocr_job_id,
            model_name="synthetic-ocr",
            model_version="test-only",
            version=1,
            documents=[
                OcrDocumentResponse(
                    document_id=801,
                    document_type=OcrDocumentType.EMR,
                    raw_text="합성 OCR 원문",
                )
            ],
            fields=[self.field()],
        )

    async def fields(self, ocr_job_id: str, actor: OcrActor, field_type: str | None) -> list[OcrFieldResponse]:
        assert ocr_job_id == "ocr_synthetic_501"
        assert actor == STAFF
        assert field_type in {None, "DIAGNOSIS"}
        return [self.field()]

    async def update_field(
        self, ocr_field_id: int, request: UpdateOcrFieldRequest, actor: OcrActor
    ) -> OcrFieldResponse:
        self.updated = (ocr_field_id, request, actor)
        return OcrFieldResponse(
            ocr_field_id=ocr_field_id,
            field_type="DIAGNOSIS",
            extracted_value="합성 추출값",
            corrected_value=request.corrected_value,
            value=request.corrected_value or "합성 추출값",
            confidence=0.83,
            version=request.base_version + 1,
            is_confirmed=request.confirm,
            modified_by=actor.staff_id,
            modified_at=NOW,
            confirmed_by=actor.staff_id if request.confirm else None,
            confirmed_at=NOW if request.confirm else None,
        )


@pytest.fixture
def api() -> tuple[TestClient, FakeOcrService]:
    app = FastAPI()
    fake = FakeOcrService()
    register_error_handlers(app)
    app.include_router(ocr_router, prefix="/api/v1")
    app.dependency_overrides[get_ocr_actor] = lambda: STAFF
    app.dependency_overrides[get_ocr_service] = lambda: fake

    @app.exception_handler(OcrApiError)
    async def handle_ocr_error(_, exc: OcrApiError):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message, "field_errors": None},
        )

    return TestClient(app), fake


def test_start_ocr_returns_processing_job(api: tuple[TestClient, FakeOcrService]) -> None:
    client, _ = api
    response = client.post(
        "/api/v1/documents/801/ocr",
        json={"visit_id": 501, "document_type": "EMR"},
    )

    assert response.status_code == 202
    assert response.json()["ocr_job_id"] == "ocr_synthetic_501"
    assert response.json()["status"] == "PROCESSING"
    assert response.json()["started_at"] is None


def test_other_hospital_resource_is_hidden_as_not_found(api: tuple[TestClient, FakeOcrService]) -> None:
    client, _ = api
    response = client.get("/api/v1/ocr/jobs/ocr_other_hospital")

    assert response.status_code == 404
    assert response.json() == {
        "code": "NOT_FOUND",
        "message": "OCR 리소스를 찾을 수 없습니다.",
        "field_errors": None,
    }


def test_result_and_structured_fields_are_returned(api: tuple[TestClient, FakeOcrService]) -> None:
    client, _ = api

    result = client.get("/api/v1/ocr/jobs/ocr_synthetic_501/result")
    fields = client.get("/api/v1/ocr/jobs/ocr_synthetic_501/fields", params={"field_type": "DIAGNOSIS"})

    assert result.status_code == 200
    assert result.headers["cache-control"] == "no-store"
    assert result.json()["documents"][0]["raw_text"] == "합성 OCR 원문"
    assert result.json()["fields"][0]["confidence"] == 0.83
    assert fields.status_code == 200
    assert fields.json()[0]["field_type"] == "DIAGNOSIS"


def test_field_update_keeps_version_and_audit_actor(api: tuple[TestClient, FakeOcrService]) -> None:
    client, fake = api
    response = client.patch(
        "/api/v1/ocr/fields/91",
        json={"base_version": 2, "corrected_value": "합성 수정값", "confirm": True},
    )

    assert response.status_code == 200
    assert response.json()["version"] == 3
    assert response.json()["confirmed_by"] == STAFF.staff_id
    assert fake.updated is not None
    assert fake.updated[2] == STAFF


def test_field_can_be_confirmed_without_rewriting_extracted_value(api: tuple[TestClient, FakeOcrService]) -> None:
    client, fake = api

    response = client.patch(
        "/api/v1/ocr/fields/91",
        json={"base_version": 1, "confirm": True},
    )

    assert response.status_code == 200
    assert response.json()["corrected_value"] is None
    assert response.json()["value"] == "합성 추출값"
    assert response.json()["is_confirmed"] is True
    assert fake.updated is not None
    assert fake.updated[1].corrected_value is None


def test_field_update_rejects_empty_or_ambiguous_value(api: tuple[TestClient, FakeOcrService]) -> None:
    client, _ = api

    empty = client.patch("/api/v1/ocr/fields/91", json={"base_version": 1, "corrected_value": "  "})
    ambiguous = client.patch(
        "/api/v1/ocr/fields/91",
        json={"base_version": 1, "corrected_value": "합성값", "candidate_id": 7},
    )

    assert empty.status_code == 422
    assert "input" not in empty.text
    assert "합성" not in empty.text
    assert ambiguous.status_code == 422
    assert "input" not in ambiguous.text
    assert "합성값" not in ambiguous.text


@pytest.mark.asyncio
async def test_admin_alone_is_denied() -> None:
    """`admin` 은 역할이 아니라 권한이다 — 혼자서는 진료 화면을 열지 못한다."""
    admin_only = SimpleNamespace(staff_id=1, hospital_id=3, roles=["admin"])

    with pytest.raises(OcrApiError, match="OCR 접근 권한") as admin_error:
        await get_ocr_actor(cast(Staff, admin_only))

    assert admin_error.value.status_code == 403


@pytest.mark.asyncio
async def test_staff_or_doctor_actor_is_allowed() -> None:
    staff_user = SimpleNamespace(staff_id=3, hospital_id=9, roles=["staff"])
    doctor_user = SimpleNamespace(staff_id=4, hospital_id=9, roles=["doctor", "admin"])

    staff = await get_ocr_actor(cast(Staff, staff_user))
    doctor = await get_ocr_actor(cast(Staff, doctor_user))

    assert staff.roles == frozenset({"staff"})
    assert staff.staff_id == 3
    assert staff.hospital_id == 9
    assert doctor.roles == frozenset({"doctor", "admin"})
    assert doctor.staff_id == 4
