"""안내문 승인·반려가 규칙대로 도는가 — KEY-111 (`KEY-76` 인수조건).

여기서 지키려는 것은 대부분 **막는 일**이라 눈으로 확인하기 어렵다.
그래서 하나씩 검사로 못 박는다.

`KEY-87`(유가은)이 감사 이벤트의 내용과 재승인 흐름을 더 깊게 볼 예정이라,
이 파일은 **API 단위의 정상·예외까지만** 본다.
"""

from typing import Any

from httpx import ASGITransport, AsyncClient
from tortoise.contrib.test import TestCase

from app.core.utils.security import hash_password
from app.main import app
from app.models.patients import Patient
from app.models.staffs import Hospital, Staff
from app.models.visits import (
    GuideDocument,
    GuideEvent,
    GuideEventType,
    GuideSection,
    GuideSectionKey,
    GuideStatus,
    Visit,
)

BASE = "/api/v1/visits"


async def make_clinic(name: str = "여성의원") -> Hospital:
    return await Hospital.create(name=name)


async def make_staff(hospital: Hospital, login_id: str, roles: list[str]) -> Staff:
    return await Staff.create(
        hospital=hospital,
        login_id=login_id,
        password_hash=hash_password("Password123!"),
        name="합성직원",
        roles=roles,
        must_change_password=False,
    )


async def make_guide(hospital: Hospital, status: GuideStatus = GuideStatus.APPROVAL_PENDING) -> GuideDocument:
    patient = await Patient.create(
        hospital_id=hospital.hospital_id,
        hospital_patient_no="SYN-12345",
        name="합성환자",
        birth_date="1990-01-01",
        phone="01044524085",
        sms_consent=True,
    )
    visit = await Visit.create(
        hospital_id=hospital.hospital_id,
        patient=patient,
        visited_at="2026-08-13T01:32:00+00:00",
    )
    guide = await GuideDocument.create(
        hospital_id=hospital.hospital_id,
        visit=visit,
        status=status,
    )
    await GuideSection.create(
        guide_document=guide,
        section_key=GuideSectionKey.MEDICATION,
        generated_body="합성 복약지도 본문",
        warn="합성 확인 부탁 문구",
    )
    await GuideSection.create(
        guide_document=guide,
        section_key=GuideSectionKey.CAUTION,
        generated_body="합성 주의사항 본문",
        # 🚨 응급 문장. 식약처 정보 기준이라 사람이 고칠 수 없다.
        locked=True,
    )
    return guide


class GuideTestCase(TestCase):
    async def sign_in(self, staff: Staff) -> dict[str, str]:
        """로그인을 거치지 않고 토큰을 만든다.

        이 검사가 보려는 것은 **승인 규칙**이지 로그인이 아니다. 로그인 계약이
        바뀔 때마다 상관없는 검사가 함께 깨지면 무엇이 진짜 고장인지 안 보인다.
        """
        from app.services.staff_auth import StaffSessionService
        from app.tests.fakes import FakeRedis

        access, _ = await StaffSessionService(FakeRedis()).start(staff, False)  # type: ignore[arg-type]
        return {"Authorization": f"Bearer {access}"}

    def client(self) -> AsyncClient:
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


class TestOnlyDoctorsApprove(GuideTestCase):
    """`admin` 은 역할이 아니라 권한이다 — 켠다고 의료 판단이 열리지 않는다."""

    async def _try_approve(self, roles: list[str], login_id: str) -> Any:
        clinic = await make_clinic()
        guide = await make_guide(clinic)
        staff = await make_staff(clinic, login_id, roles)

        async with self.client() as client:
            return await client.post(f"{BASE}/{guide.visit_id}/guide/approve", headers=await self.sign_in(staff))

    async def test_a_doctor_can_approve(self) -> None:
        response = await self._try_approve(["doctor"], "doctor01")
        assert response.status_code == 200
        assert response.json()["status"] == GuideStatus.SCHEDULED_TO_SEND

    async def test_a_staff_cannot(self) -> None:
        response = await self._try_approve(["staff"], "staff01")
        assert response.status_code == 403

    async def test_an_admin_alone_cannot(self) -> None:
        """운영 권한만으로는 안내문을 환자에게 내보낼 수 없다."""
        response = await self._try_approve(["admin"], "admin01")
        assert response.status_code == 403

    async def test_a_staff_who_is_also_admin_cannot(self) -> None:
        response = await self._try_approve(["staff", "admin"], "adminstaff01")
        assert response.status_code == 403

    async def test_a_doctor_who_is_also_admin_can(self) -> None:
        """admin 을 겸해도 의사는 의사다 — admin 이 승인을 방해하지 않는다."""
        response = await self._try_approve(["doctor", "admin"], "admindoc01")
        assert response.status_code == 200


class TestApprovalSchedulesTheSend(GuideTestCase):
    """승인이 곧 발송 예약이다 — 스탭이 발송 버튼을 누르지 않는다(D1-5)."""

    async def test_approving_fills_the_schedule(self) -> None:
        clinic = await make_clinic()
        guide = await make_guide(clinic)
        doctor = await make_staff(clinic, "doctor01", ["doctor"])

        async with self.client() as client:
            response = await client.post(f"{BASE}/{guide.visit_id}/guide/approve", headers=await self.sign_in(doctor))

        body = response.json()
        assert body["status"] == GuideStatus.SCHEDULED_TO_SEND
        assert body["approved_at"], "누가 언제 승인했는지가 비어 있다"
        assert body["scheduled_at"], "승인했는데 발송 예정 시각이 없다"

        saved = await GuideDocument.get(guide_document_id=guide.guide_document_id)
        assert saved.approved_by == doctor.staff_id

    async def test_approving_twice_is_refused(self) -> None:
        """두 번 승인을 조용히 넘기면 발송 예정 시각이 밀린다."""
        clinic = await make_clinic()
        guide = await make_guide(clinic)
        doctor = await make_staff(clinic, "doctor01", ["doctor"])

        async with self.client() as client:
            headers = await self.sign_in(doctor)
            first = await client.post(f"{BASE}/{guide.visit_id}/guide/approve", headers=headers)
            again = await client.post(f"{BASE}/{guide.visit_id}/guide/approve", headers=headers)

        assert first.status_code == 200
        assert again.status_code == 409
        assert again.json()["code"] == "ALREADY_APPROVED"

    async def test_a_draft_cannot_be_approved(self) -> None:
        """스탭이 아직 확인 중인 것을 건너뛰어 승인할 수 없다."""
        clinic = await make_clinic()
        guide = await make_guide(clinic, status=GuideStatus.STAFF_REVIEW)
        doctor = await make_staff(clinic, "doctor01", ["doctor"])

        async with self.client() as client:
            response = await client.post(f"{BASE}/{guide.visit_id}/guide/approve", headers=await self.sign_in(doctor))

        assert response.status_code == 409
        assert response.json()["code"] == "GUIDE_NOT_PENDING"


class TestReturnNeedsAReason(GuideTestCase):
    """사유가 스탭 알림에 그대로 뜬다 — 비어 있으면 무엇을 고칠지 모른다."""

    async def test_a_reason_is_required(self) -> None:
        clinic = await make_clinic()
        guide = await make_guide(clinic)
        doctor = await make_staff(clinic, "doctor01", ["doctor"])

        async with self.client() as client:
            headers = await self.sign_in(doctor)
            empty = await client.post(f"{BASE}/{guide.visit_id}/guide/return", json={"reason": "   "}, headers=headers)
            missing = await client.post(f"{BASE}/{guide.visit_id}/guide/return", json={}, headers=headers)

        assert empty.status_code == 422
        assert missing.status_code == 422

    async def test_the_reason_is_kept(self) -> None:
        clinic = await make_clinic()
        guide = await make_guide(clinic)
        doctor = await make_staff(clinic, "doctor01", ["doctor"])

        async with self.client() as client:
            response = await client.post(
                f"{BASE}/{guide.visit_id}/guide/return",
                json={"reason": "진료기록 재업로드 필요"},
                headers=await self.sign_in(doctor),
            )

        assert response.status_code == 200
        assert response.json()["status"] == GuideStatus.APPROVAL_RETURNED
        assert response.json()["returned_reason"] == "진료기록 재업로드 필요"

        event = await GuideEvent.filter(guide_document_id=guide.guide_document_id).first()
        assert event is not None
        assert event.event_type is GuideEventType.RETURNED
        assert event.reason == "진료기록 재업로드 필요", "이력에 사유가 안 남으면 나중에 되짚을 수 없다"


class TestHistoryIsKept(GuideTestCase):
    """상태만 바뀌고 이력이 비면 「누가 내보냈나」에 답할 수 없다."""

    async def test_approving_leaves_a_trace(self) -> None:
        clinic = await make_clinic()
        guide = await make_guide(clinic)
        doctor = await make_staff(clinic, "doctor01", ["doctor"])

        async with self.client() as client:
            await client.post(f"{BASE}/{guide.visit_id}/guide/approve", headers=await self.sign_in(doctor))

        events = await GuideEvent.filter(guide_document_id=guide.guide_document_id)
        assert len(events) == 1
        assert events[0].event_type is GuideEventType.APPROVED
        assert events[0].actor_id == doctor.staff_id

    async def test_editing_leaves_a_trace_and_keeps_the_original(self) -> None:
        clinic = await make_clinic()
        guide = await make_guide(clinic)
        doctor = await make_staff(clinic, "doctor01", ["doctor"])

        async with self.client() as client:
            response = await client.patch(
                f"{BASE}/{guide.visit_id}/guide/sections/medication",
                json={"body": "원장님이 고친 본문"},
                headers=await self.sign_in(doctor),
            )

        assert response.status_code == 200
        assert response.json()["body"] == "원장님이 고친 본문"
        assert response.json()["edited"] is True

        section = await GuideSection.get(
            guide_document_id=guide.guide_document_id, section_key=GuideSectionKey.MEDICATION
        )
        assert section.generated_body == "합성 복약지도 본문", "생성 원문이 지워졌다 — 다음 초안 개선에 쓸 수 없다"

        event = await GuideEvent.filter(guide_document_id=guide.guide_document_id).first()
        assert event is not None
        assert event.event_type is GuideEventType.EDITED
        assert event.section_key is GuideSectionKey.MEDICATION


class TestLockedSectionStaysLocked(GuideTestCase):
    """🚨 응급 문장은 식약처 정보 기준이라 사람이 고칠 수 없다(D1-2)."""

    async def test_editing_it_is_refused(self) -> None:
        clinic = await make_clinic()
        guide = await make_guide(clinic)
        doctor = await make_staff(clinic, "doctor01", ["doctor"])

        async with self.client() as client:
            response = await client.patch(
                f"{BASE}/{guide.visit_id}/guide/sections/caution",
                json={"body": "고쳐 보겠습니다"},
                headers=await self.sign_in(doctor),
            )

        assert response.status_code == 409
        assert response.json()["code"] == "SECTION_LOCKED"


class TestOtherClinicIsHidden(GuideTestCase):
    """타 병원 것은 `403` 이 아니라 `404` 다 — 존재 여부를 감춘다(계약 §5)."""

    async def test_it_answers_not_found(self) -> None:
        mine = await make_clinic("우리의원")
        theirs = await make_clinic("옆의원")
        guide = await make_guide(theirs)
        doctor = await make_staff(mine, "doctor01", ["doctor"])

        async with self.client() as client:
            headers = await self.sign_in(doctor)
            read = await client.get(f"{BASE}/{guide.visit_id}/guide", headers=headers)
            approve = await client.post(f"{BASE}/{guide.visit_id}/guide/approve", headers=headers)

        assert read.status_code == 404
        assert approve.status_code == 404, "남의 의원 것을 승인 시도했을 때 403 이면 존재가 새어 나간다"


class TestReadingTheGuide(GuideTestCase):
    async def test_it_returns_what_the_screen_needs(self) -> None:
        clinic = await make_clinic()
        guide = await make_guide(clinic)
        doctor = await make_staff(clinic, "doctor01", ["doctor"])

        async with self.client() as client:
            response = await client.get(f"{BASE}/{guide.visit_id}/guide", headers=await self.sign_in(doctor))

        body = response.json()
        assert response.status_code == 200
        assert body["status"] == GuideStatus.APPROVAL_PENDING
        keys = [s["key"] for s in body["sections"]]
        assert keys == [GuideSectionKey.MEDICATION, GuideSectionKey.CAUTION]

        medication = body["sections"][0]
        assert medication["warn"] == "합성 확인 부탁 문구", "⚠ 는 서버가 판정한다 — 화면이 알 수 없다"
        assert body["sections"][1]["locked"] is True
