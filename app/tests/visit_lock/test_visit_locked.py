"""후속 데이터가 붙은 진료의 식별 관계를 잠근다 — KEY-135 (계약 §6·§7).

**왜 막는가.** 안내문 본문은 이 진료의 맥락으로 쓰인다. 승인해서 발송을
기다리는 안내가 달린 진료의 진료과를 바꾸면, 나가는 글과 기록이 가리키는 곳이
갈라진다. `guide_event` 에는 「승인했다」만 남아 있어 무엇을 승인한 것이었는지
되짚을 수 없다. 의무기록이라 조용히 어긋나면 복구할 근거가 없다.

**과하게 걸리지 않는 것까지 본다.** 잠금은 붙이기는 쉽고 걷어내기는 어렵다 —
아무것도 안 붙은 진료가 잠기거나, 진료 내용 필드까지 막히면 스탭이 일을 못 한다.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient, Response
from starlette import status
from tortoise.contrib.test import TestCase

from app.dependencies.patient_access import ClinicalActor, get_clinical_actor
from app.main import app
from app.models.ocr import OcrJob, OcrJobStatus
from app.models.patients import Patient
from app.models.visits import GuideDocument, GuideStatus, Visit

BASE = "http://test"
HOSPITAL_ID = 1
OTHER_HOSPITAL_ID = 2


@asynccontextmanager
async def client_for(actor: ClinicalActor) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_clinical_actor] = lambda: actor
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_clinical_actor, None)


async def make_visit(hospital_id: int = HOSPITAL_ID, chart: str = "SYN-LOCK-01") -> Visit:
    patient = await Patient.create(
        hospital_id=hospital_id,
        hospital_patient_no=chart,
        name="합성환자",
        birth_date="1994-07-22",
        phone="01039457702",
        sms_consent=True,
    )
    return await Visit.create(
        hospital_id=hospital_id,
        patient=patient,
        visited_at=datetime(2026, 8, 19, 1, 30, tzinfo=UTC),
    )


async def attach_ocr(visit: Visit) -> None:
    await OcrJob.create(
        ocr_job_id=f"syn-lock-{visit.visit_id}",
        hospital_id=visit.hospital_id,
        visit_id=visit.visit_id,
        requested_by=101,
        status=OcrJobStatus.PROCESSING,
    )


async def attach_guide(visit: Visit, guide_status: GuideStatus) -> None:
    await GuideDocument.create(hospital_id=visit.hospital_id, visit_id=visit.visit_id, status=guide_status)


class VisitLockTestCase(TestCase):
    staff = ClinicalActor(staff_id=101, hospital_id=HOSPITAL_ID, roles=frozenset({"staff"}))

    async def patch(self, visit_id: int, body: dict[str, object]) -> Response:
        async with client_for(self.staff) as client:
            return await client.patch(f"/api/v1/visits/{visit_id}", json=body)


class TestLockedAfterFollowUpData(VisitLockTestCase):
    async def test_ocr_locks_the_department(self) -> None:
        visit = await make_visit()
        await attach_ocr(visit)

        response = await self.patch(visit.visit_id, {"department_id": 7})

        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.json()["code"] == "VISIT_LOCKED"

    async def test_a_guide_waiting_for_approval_locks_the_department(self) -> None:
        visit = await make_visit()
        await attach_guide(visit, GuideStatus.APPROVAL_PENDING)

        response = await self.patch(visit.visit_id, {"department_id": 7})

        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.json()["code"] == "VISIT_LOCKED"

    async def test_an_approved_guide_locks_the_department(self) -> None:
        """이것이 가장 위험한 자리 — 이미 나갈 준비가 된 글이다."""
        visit = await make_visit()
        await attach_guide(visit, GuideStatus.SCHEDULED_TO_SEND)

        response = await self.patch(visit.visit_id, {"department_id": 7})

        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.json()["code"] == "VISIT_LOCKED"


class TestTheLockIsNotTooWide(VisitLockTestCase):
    """붙이기는 쉽고 걷어내기는 어렵다. 안 걸려야 할 것을 함께 못 박는다."""

    async def test_a_bare_visit_still_changes(self) -> None:
        visit = await make_visit()

        response = await self.patch(visit.visit_id, {"department_id": 7})

        assert response.status_code != status.HTTP_409_CONFLICT, "아무것도 안 붙은 진료가 잠겼다"

    async def test_content_fields_stay_editable_on_a_locked_visit(self) -> None:
        """진료 내용은 식별 관계가 아니다 — 잠긴 진료에서도 계속 적을 수 있어야 한다."""
        visit = await make_visit()
        await attach_guide(visit, GuideStatus.SCHEDULED_TO_SEND)

        response = await self.patch(
            visit.visit_id,
            {"visit_summary": "승인 뒤에 적은 메모", "doctor_note": "환자가 전화로 알려온 것", "planned_stop": True},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["visit_summary"] == "승인 뒤에 적은 메모"

    async def test_a_draft_guide_does_not_lock(self) -> None:
        """스탭이 아직 쓰고 있는 중이다 — 진료과가 잘못 잡힌 것을 그때 고쳐야 한다."""
        visit = await make_visit()
        await attach_guide(visit, GuideStatus.STAFF_REVIEW)

        response = await self.patch(visit.visit_id, {"department_id": 7})

        assert response.status_code != status.HTTP_409_CONFLICT

    async def test_a_returned_guide_does_not_lock(self) -> None:
        """되돌려진 안내는 스탭이 고치는 중이다. 여기서 잠그면 고칠 방법이 없다."""
        visit = await make_visit()
        await attach_guide(visit, GuideStatus.APPROVAL_RETURNED)

        response = await self.patch(visit.visit_id, {"department_id": 7})

        assert response.status_code != status.HTTP_409_CONFLICT

    async def test_another_hospital_visit_is_still_not_found(self) -> None:
        """잠금 여부로 남의 병원 진료의 존재가 새면 안 된다 — 409 가 아니라 404 다."""
        visit = await make_visit(OTHER_HOSPITAL_ID, chart="SYN-LOCK-99")
        await attach_guide(visit, GuideStatus.SCHEDULED_TO_SEND)

        response = await self.patch(visit.visit_id, {"department_id": 7})

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.json()["code"] == "VISIT_NOT_FOUND"
