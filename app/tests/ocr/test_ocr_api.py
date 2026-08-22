from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.error_handlers import register_error_handlers
from app.models.ocr import OcrDocumentText, OcrDocumentType, OcrField, OcrJobStatus
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
from app.ocr.service import LOW_CONFIDENCE_THRESHOLD, serialize_field

NOW = datetime(2026, 8, 19, 8, 0, tzinfo=UTC)
STAFF = OcrActor(staff_id=17, hospital_id=3, roles=frozenset({"staff"}))


class FakeOcrService:
    def __init__(self) -> None:
        self.updated: tuple[int, UpdateOcrFieldRequest, OcrActor] | None = None
        self.pending: bool = False

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
    def field(*, pending: bool = False) -> OcrFieldResponse:
        return OcrFieldResponse(
            ocr_field_id=91,
            field_type="DIAGNOSIS",
            extracted_value="합성 추출값",
            corrected_value=None,
            value="합성 추출값",
            unit="mg/dL",
            confidence=0.83,
            is_low_confidence=False,
            version=1,
            is_confirmed=False,
            is_pending_report=pending,
            document_id=801,
            source_line=12,
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
        return [self.field(pending=self.pending)]

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
            unit="mg/dL",
            confidence=0.83,
            is_low_confidence=False,
            version=request.base_version + 1,
            is_confirmed=request.confirm,
            is_pending_report=False,
            document_id=801,
            source_line=12,
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


def test_field_contract_fields_are_present_in_response(api: tuple[TestClient, FakeOcrService]) -> None:
    client, _ = api
    response = client.get("/api/v1/ocr/jobs/ocr_synthetic_501/fields", params={"field_type": "DIAGNOSIS"})

    assert response.status_code == 200
    field = response.json()[0]
    assert field["unit"] == "mg/dL"
    assert field["is_low_confidence"] is False
    assert field["is_pending_report"] is False
    assert field["document_id"] == 801
    assert field["source_line"] == 12


def test_low_confidence_flag_is_set_by_server() -> None:
    """confidence < 0.75이면 is_low_confidence=True — 화면이 임계값을 임의로 정하지 않는다."""
    low = OcrField(ocr_field_id=1, field_type="X", confidence=LOW_CONFIDENCE_THRESHOLD - 0.01)
    high = OcrField(ocr_field_id=2, field_type="Y", confidence=LOW_CONFIDENCE_THRESHOLD)
    null_conf = OcrField(ocr_field_id=3, field_type="Z", confidence=None)

    assert serialize_field(low).is_low_confidence is True
    assert serialize_field(high).is_low_confidence is False
    assert serialize_field(null_conf).is_low_confidence is False


def test_document_id_is_hidden_after_raw_text_purge() -> None:
    """원문 파기 후에는 document_id를 None으로 반환해 우회 노출을 막는다."""
    active_doc = OcrDocumentText(ocr_document_text_id=1, document_id=801, raw_text_purged_at=None)
    purged_doc = OcrDocumentText(
        ocr_document_text_id=2, document_id=801, raw_text_purged_at=datetime(2026, 8, 21, tzinfo=UTC)
    )

    field_with_active = OcrField(ocr_field_id=10, field_type="DIAGNOSIS")
    field_with_active.document_text_id = 1

    field_with_purged = OcrField(ocr_field_id=11, field_type="DIAGNOSIS")
    field_with_purged.document_text_id = 2

    field_no_doc = OcrField(ocr_field_id=12, field_type="DIAGNOSIS")

    doc_map = {1: active_doc, 2: purged_doc}

    assert serialize_field(field_with_active, doc_map).document_id == 801
    assert serialize_field(field_with_purged, doc_map).document_id is None
    assert serialize_field(field_no_doc, doc_map).document_id is None


def test_pending_report_field_is_exposed_in_api_response(api: tuple[TestClient, FakeOcrService]) -> None:
    """is_pending_report=True 플래그가 API 응답에 노출된다."""
    client, fake = api

    fake.pending = True
    try:
        response = client.get("/api/v1/ocr/jobs/ocr_synthetic_501/fields", params={"field_type": "DIAGNOSIS"})
        assert response.status_code == 200
        assert response.json()[0]["is_pending_report"] is True
    finally:
        fake.pending = False


def test_pending_report_flag_does_not_null_value_or_document_id() -> None:
    """is_pending_report=True여도 서버는 value·document_id를 지우지 않는다.

    is_pending_report는 "추후 보고 예정"을 나타내는 상태 플래그이며,
    값 표시 방식은 화면이 플래그를 보고 결정한다. OCR이 수치를 추출했다면
    서버는 그대로 내려주고, document_id도 raw_text_purged_at만 본다.
    """
    field = OcrField(ocr_field_id=1, field_type="AMH", extracted_value="1.2", is_pending_report=True)
    field.document_text_id = 1
    doc = OcrDocumentText(ocr_document_text_id=1, document_id=801, raw_text_purged_at=None)

    result = serialize_field(field, {1: doc})

    assert result.is_pending_report is True
    assert result.value == "1.2"
    assert result.document_id == 801
