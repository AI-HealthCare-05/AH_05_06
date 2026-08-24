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
from app.models.staffs import Hospital, Staff
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


async def attach_ocr(visit: Visit, status_value: OcrJobStatus = OcrJobStatus.PROCESSING) -> None:
    await OcrJob.create(
        ocr_job_id=f"syn-lock-{visit.visit_id}",
        hospital_id=visit.hospital_id,
        visit_id=visit.visit_id,
        requested_by=101,
        status=status_value,
    )


async def attach_guide(visit: Visit, guide_status: GuideStatus) -> None:
    await GuideDocument.create(hospital_id=visit.hospital_id, visit_id=visit.visit_id, status=guide_status)


async def make_doctor(hospital_id: int = HOSPITAL_ID, suffix: str = "01") -> Staff:
    hospital, _ = await Hospital.get_or_create(hospital_id=hospital_id, defaults={"name": f"합성병원-{hospital_id}"})
    return await Staff.create(
        hospital=hospital,
        login_id=f"syn-lock-doctor-{hospital_id}-{suffix}",
        password_hash="synthetic-not-a-real-hash",
        name=f"합성의사-{suffix}",
        roles=["doctor"],
    )


class VisitLockTestCase(TestCase):
    staff = ClinicalActor(staff_id=101, hospital_id=HOSPITAL_ID, roles=frozenset({"staff"}))

    async def patch(self, visit_id: int, body: dict[str, object]) -> Response:
        async with client_for(self.staff) as client:
            return await client.patch(f"/api/v1/visits/{visit_id}", json=body)


class TestLockedAfterFollowUpData(VisitLockTestCase):
    async def test_processing_and_completed_ocr_lock_all_identity_relations(self) -> None:
        cases: tuple[tuple[str, dict[str, object]], ...] = (
            ("department_id", {"department_id": None}),
            ("doctor_id", {"doctor_id": 9001}),
            ("visited_at", {"visited_at": "2026-08-20T10:30:00+09:00"}),
        )
        for ocr_status in (OcrJobStatus.PROCESSING, OcrJobStatus.COMPLETED):
            for index, (field, body) in enumerate(cases):
                with self.subTest(status=ocr_status, field=field):
                    visit = await make_visit(chart=f"SYN-OCR-{ocr_status}-{index}")
                    if field == "department_id":
                        visit.department = "합성진료과"
                        await visit.save(update_fields=["department"])
                    await attach_ocr(visit, ocr_status)

                    response = await self.patch(visit.visit_id, body)

                    assert response.status_code == status.HTTP_409_CONFLICT
                    assert response.json()["code"] == "VISIT_LOCKED"

    async def test_pending_and_approved_guides_lock_all_identity_relations(self) -> None:
        cases: tuple[tuple[str, dict[str, object]], ...] = (
            ("department_id", {"department_id": None}),
            ("doctor_id", {"doctor_id": 9001}),
            ("visited_at", {"visited_at": "2026-08-20T10:30:00+09:00"}),
        )
        for guide_status in (GuideStatus.APPROVAL_PENDING, GuideStatus.SCHEDULED_TO_SEND):
            for index, (field, body) in enumerate(cases):
                with self.subTest(status=guide_status, field=field):
                    visit = await make_visit(chart=f"SYN-GUIDE-{guide_status}-{index}")
                    if field == "department_id":
                        visit.department = "합성진료과"
                        await visit.save(update_fields=["department"])
                    await attach_guide(visit, guide_status)

                    response = await self.patch(visit.visit_id, body)

                    assert response.status_code == status.HTTP_409_CONFLICT
                    assert response.json()["code"] == "VISIT_LOCKED"


class TestTheLockIsNotTooWide(VisitLockTestCase):
    """붙이기는 쉽고 걷어내기는 어렵다. 안 걸려야 할 것을 함께 못 박는다."""

    async def test_a_bare_visit_still_changes_all_supported_identity_relations(self) -> None:
        doctor = await make_doctor()
        doctor_visit = await make_visit(chart="SYN-BARE-DOCTOR")
        doctor_response = await self.patch(doctor_visit.visit_id, {"doctor_id": doctor.staff_id})
        assert doctor_response.status_code == status.HTTP_200_OK

        date_visit = await make_visit(chart="SYN-BARE-DATE")
        date_response = await self.patch(date_visit.visit_id, {"visited_at": "2026-08-20T10:30:00+09:00"})
        assert date_response.status_code == status.HTTP_200_OK

        department_visit = await make_visit(chart="SYN-BARE-DEPARTMENT")
        department_visit.department = "합성진료과"
        await department_visit.save(update_fields=["department"])
        department_response = await self.patch(department_visit.visit_id, {"department_id": None})
        assert department_response.status_code == status.HTTP_200_OK
        assert department_response.json()["department"] is None

    async def test_content_fields_stay_editable_on_a_locked_visit(self) -> None:
        """진료 내용은 식별 관계가 아니다 — 잠긴 진료에서도 계속 적을 수 있어야 한다."""
        visit = await make_visit()
        await attach_ocr(visit)

        response = await self.patch(
            visit.visit_id,
            {
                "visit_summary": "승인 뒤에 적은 합성 메모",
                "doctor_note": "합성 후속 기록",
                "status": "SCHEDULED",
                "planned_stop": True,
            },
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["visit_summary"] == "승인 뒤에 적은 합성 메모"

    async def test_failed_ocr_alone_does_not_lock(self) -> None:
        doctor = await make_doctor()
        visit = await make_visit(chart="SYN-FAILED-OCR")
        await attach_ocr(visit, OcrJobStatus.FAILED)

        response = await self.patch(visit.visit_id, {"doctor_id": doctor.staff_id})

        assert response.status_code == status.HTTP_200_OK

    async def test_a_processing_retry_still_locks_after_a_failed_job(self) -> None:
        visit = await make_visit(chart="SYN-FAILED-RETRY")
        await attach_ocr(visit, OcrJobStatus.FAILED)
        await OcrJob.create(
            ocr_job_id=f"syn-lock-retry-{visit.visit_id}",
            hospital_id=visit.hospital_id,
            visit_id=visit.visit_id,
            requested_by=101,
            status=OcrJobStatus.PROCESSING,
        )

        response = await self.patch(visit.visit_id, {"visited_at": "2026-08-20T10:30:00+09:00"})

        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.json()["code"] == "VISIT_LOCKED"

    async def test_resending_the_same_identity_values_is_allowed_while_locked(self) -> None:
        doctor = await make_doctor()
        visited_at = datetime(2026, 8, 19, 1, 30, tzinfo=UTC)
        visit = await make_visit(chart="SYN-SAME-VALUES")
        visit.doctor_id = doctor.staff_id
        visit.visited_at = visited_at
        await visit.save(update_fields=["doctor_id", "visited_at"])
        await visit.refresh_from_db()
        await attach_ocr(visit, OcrJobStatus.COMPLETED)

        responses = [
            await self.patch(visit.visit_id, {"doctor_id": doctor.staff_id}),
            await self.patch(visit.visit_id, {"department_id": None}),
            await self.patch(visit.visit_id, {"visited_at": visit.visited_at.isoformat()}),
        ]

        assert [response.status_code for response in responses] == [
            status.HTTP_200_OK,
            status.HTTP_200_OK,
            status.HTTP_200_OK,
        ]

    async def test_a_draft_guide_alone_does_not_lock(self) -> None:
        """안내문 상태만 놓고 보면 「작성 중」은 잠그지 않는다.

        **이것은 안내문 가지만 따로 재는 검사다.** 실제 운영에서 이 조합은
        일어나지 않는다 — 안내문은 늘 OCR 확정 뒤에 생기므로 그 진료에는
        `OcrJob` 이 이미 있고, OCR 가지에서 먼저 409 가 난다.
        진짜 조합은 `test_ocr_wins_over_a_draft_guide` 가 잰다.
        """
        visit = await make_visit()
        await attach_guide(visit, GuideStatus.STAFF_REVIEW)

        response = await self.patch(visit.visit_id, {"department_id": 7})

        assert response.status_code != status.HTTP_409_CONFLICT

    async def test_a_returned_guide_alone_does_not_lock(self) -> None:
        """되돌려진 안내도 안내문 가지에서는 잠그지 않는다.

        위와 같다 — 안내문 가지만 따로 재는 검사다.
        """
        visit = await make_visit()
        await attach_guide(visit, GuideStatus.APPROVAL_RETURNED)

        response = await self.patch(visit.visit_id, {"department_id": 7})

        assert response.status_code != status.HTTP_409_CONFLICT


class TestOcrDecidesFirst(VisitLockTestCase):
    """**진행·완료 OCR이 있으면 안내문 상태와 무관하게 잠긴다.**

    계약 §6 은 「OCR **또는** 승인 안내가 이미 연결된 뒤」라고 적는다. **또는**
    이므로 OCR 하나만으로 충분하고, 안내문 상태는 그다음에야 본다.

    그런데 안내문은 늘 OCR 확정 뒤에 생긴다. 그래서 **스탭이 실제로 마주치는
    조합은 언제나 「OCR 있음 + 안내문 어떤 상태」** 이고, 그 경우 답은 항상
    409 다. 「스탭이 쓰고 있는 중이면 진료과를 고칠 수 있다」는 길은
    **운영에서는 열리지 않는다.**

    이 검사들은 그 사실을 못 박는다. 나중에 규칙을 「OCR 이 `COMPLETED` 일
    때만 잠근다」처럼 잘게 나누기로 하면 여기가 먼저 죽어서 알려 준다.
    """

    async def test_ocr_wins_over_a_draft_guide(self) -> None:
        visit = await make_visit()
        await attach_ocr(visit)
        await attach_guide(visit, GuideStatus.STAFF_REVIEW)

        response = await self.patch(visit.visit_id, {"department_id": 7})

        assert response.status_code == status.HTTP_409_CONFLICT, "OCR 이 붙었는데 안 잠겼다"
        assert response.json()["code"] == "VISIT_LOCKED"

    async def test_ocr_wins_over_a_returned_guide(self) -> None:
        visit = await make_visit()
        await attach_ocr(visit)
        await attach_guide(visit, GuideStatus.APPROVAL_RETURNED)

        response = await self.patch(visit.visit_id, {"department_id": 7})

        assert response.status_code == status.HTTP_409_CONFLICT, "OCR 이 붙었는데 안 잠겼다"
        assert response.json()["code"] == "VISIT_LOCKED"

    async def test_clearing_the_department_is_also_refused(self) -> None:
        """`department_id: null` 은 아무것도 안 하는 요청이 아니다.

        받으면 `visit.department` 를 **비운다** — 진료 당시 진료과 이름의
        스냅샷이 사라지는 것이라 식별 관계 변경이 맞다. 그래서 잠긴 진료에서는
        이것도 409 다.
        """
        visit = await make_visit()
        visit.department = "합성진료과"
        await visit.save(update_fields=["department"])
        await attach_ocr(visit)

        response = await self.patch(visit.visit_id, {"department_id": None})

        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.json()["code"] == "VISIT_LOCKED"

    async def test_another_hospital_visit_is_still_not_found(self) -> None:
        """잠금 여부로 남의 병원 진료의 존재가 새면 안 된다 — 409 가 아니라 404 다."""
        visit = await make_visit(OTHER_HOSPITAL_ID, chart="SYN-LOCK-99")
        await attach_guide(visit, GuideStatus.SCHEDULED_TO_SEND)

        response = await self.patch(visit.visit_id, {"department_id": 7})

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.json()["code"] == "VISIT_NOT_FOUND"

    async def test_patient_id_is_not_an_update_field(self) -> None:
        """환자 관계는 DTO에 없으므로 잠금 이전에 공통 요청 오류로 거부된다."""
        visit = await make_visit(chart="SYN-PATIENT-ID")

        response = await self.patch(visit.visit_id, {"patient_id": 9999})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["code"] == "INVALID_REQUEST"
