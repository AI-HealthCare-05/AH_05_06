"""확정 OCR → 고정 안내 생성 연결 — KEY-150.

이 검사가 보려는 것은 **생성 게이트**다.
  · OCR 확정 전에는 안내를 만들 수 없다
  · 확정 후에는 승인 대기 안내 한 건이 만들어진다
  · caution 섹션은 locked=True — 식약처 근거 응급 문장
  · 생성 후 승인은 의사만 할 수 있다 (기존 규칙 유지)
"""

from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient
from tortoise.contrib.test import TestCase

from app.core.redis_client import get_redis
from app.core.utils.security import hash_password
from app.main import app
from app.models.ocr import OcrField, OcrJob, OcrJobStatus, OcrResult
from app.models.patients import Patient
from app.models.staffs import Hospital, Staff
from app.models.visits import GuideSectionKey, GuideStatus, Visit
from app.services.staff_auth import StaffSessionService
from app.tests.fakes import FakeRedis

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


async def make_visit(hospital: Hospital, chart: str = "SYN-GEN-01") -> Visit:
    patient = await Patient.create(
        hospital_id=hospital.hospital_id,
        hospital_patient_no=chart,
        name="합성환자",
        birth_date="1990-05-15",
        phone="01012345678",
        sms_consent=True,
    )
    return await Visit.create(
        hospital_id=hospital.hospital_id,
        patient=patient,
        visited_at=datetime(2026, 8, 22, 9, 0, tzinfo=UTC),
    )


async def attach_confirmed_ocr(visit: Visit, staff_id: int) -> OcrField:
    """visit에 완료된 OCR 잡과 확정 필드 하나를 붙인다 — W1 fixture."""
    job = await OcrJob.create(
        ocr_job_id=f"syn-gen-{visit.visit_id}",
        hospital_id=visit.hospital_id,
        visit_id=visit.visit_id,
        requested_by=staff_id,
        status=OcrJobStatus.COMPLETED,
    )
    result = await OcrResult.create(ocr_job=job, model_name="synthetic-fixture")
    return await OcrField.create(
        ocr_result=result,
        field_type="DIAGNOSIS",
        extracted_value="PCOS",
        is_confirmed=True,
        confirmed_by=staff_id,
    )


class GenerateGuideTestCase(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.redis = FakeRedis()
        app.dependency_overrides[get_redis] = lambda: self.redis

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        super().tearDown()

    async def sign_in(self, staff: Staff) -> dict[str, str]:
        access, _ = await StaffSessionService(self.redis).start(staff, False)  # type: ignore[arg-type]
        return {"Authorization": f"Bearer {access}"}

    def client(self) -> AsyncClient:
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


class TestGenerateBlocksUnconfirmedOcr(GenerateGuideTestCase):
    """OCR 미확정 상태에서는 안내를 만들 수 없다 — KEY-150 완료 조건."""

    async def test_no_ocr_at_all_is_refused(self) -> None:
        clinic = await make_clinic()
        staff = await make_staff(clinic, "staff01", ["staff"])
        visit = await make_visit(clinic)

        async with self.client() as client:
            response = await client.post(f"{BASE}/{visit.visit_id}/guide/generate", headers=await self.sign_in(staff))

        assert response.status_code == 422
        assert response.json()["code"] == "OCR_NOT_CONFIRMED"

    async def test_unconfirmed_field_is_refused(self) -> None:
        """필드가 있어도 확정(is_confirmed=True)이 아니면 막힌다."""
        clinic = await make_clinic()
        staff = await make_staff(clinic, "staff01", ["staff"])
        visit = await make_visit(clinic)

        job = await OcrJob.create(
            ocr_job_id=f"syn-unconf-{visit.visit_id}",
            hospital_id=clinic.hospital_id,
            visit_id=visit.visit_id,
            requested_by=staff.staff_id,
            status=OcrJobStatus.COMPLETED,
        )
        result = await OcrResult.create(ocr_job=job, model_name="synthetic-fixture")
        await OcrField.create(
            ocr_result=result,
            field_type="DIAGNOSIS",
            extracted_value="PCOS",
            is_confirmed=False,
        )

        async with self.client() as client:
            response = await client.post(f"{BASE}/{visit.visit_id}/guide/generate", headers=await self.sign_in(staff))

        assert response.status_code == 422
        assert response.json()["code"] == "OCR_NOT_CONFIRMED"


class TestGenerateCreatesApprovalPendingGuide(GenerateGuideTestCase):
    """확정 OCR이 있으면 승인 대기 안내 한 건이 만들어진다."""

    async def test_confirmed_ocr_creates_guide(self) -> None:
        clinic = await make_clinic()
        staff = await make_staff(clinic, "staff01", ["staff"])
        visit = await make_visit(clinic)
        await attach_confirmed_ocr(visit, staff.staff_id)

        async with self.client() as client:
            response = await client.post(f"{BASE}/{visit.visit_id}/guide/generate", headers=await self.sign_in(staff))

        assert response.status_code == 201
        body = response.json()
        assert body["status"] == GuideStatus.APPROVAL_PENDING
        assert body["visit_id"] == visit.visit_id

    async def test_all_four_sections_are_created(self) -> None:
        clinic = await make_clinic()
        staff = await make_staff(clinic, "staff01", ["staff"])
        visit = await make_visit(clinic)
        await attach_confirmed_ocr(visit, staff.staff_id)

        async with self.client() as client:
            response = await client.post(f"{BASE}/{visit.visit_id}/guide/generate", headers=await self.sign_in(staff))

        keys = {s["key"] for s in response.json()["sections"]}
        assert keys == {
            GuideSectionKey.MEDICATION,
            GuideSectionKey.CAUTION,
            GuideSectionKey.LIFE,
            GuideSectionKey.MESSAGES,
        }

    async def test_caution_is_locked_and_others_are_not(self) -> None:
        """caution만 응급 잠금이다 — 나머지는 의사가 고칠 수 있어야 한다.

        이희진 코멘트 「고정 안내 생성 경로에서 caution/emergency 분리를
        함께 확인해야 합니다」의 생성 경로 검증.
        caution이 잠겨 있다는 것만으로는 부족하다 — 다른 섹션이 함께
        잠겨 있으면 의사가 아무것도 고칠 수 없는 안내가 된다.
        """
        clinic = await make_clinic()
        staff = await make_staff(clinic, "staff01", ["staff"])
        visit = await make_visit(clinic)
        await attach_confirmed_ocr(visit, staff.staff_id)

        async with self.client() as client:
            response = await client.post(f"{BASE}/{visit.visit_id}/guide/generate", headers=await self.sign_in(staff))

        sections = {s["key"]: s for s in response.json()["sections"]}
        assert sections[GuideSectionKey.CAUTION]["locked"] is True
        assert sections[GuideSectionKey.MEDICATION]["locked"] is False
        assert sections[GuideSectionKey.LIFE]["locked"] is False
        assert sections[GuideSectionKey.MESSAGES]["locked"] is False

    async def test_medication_body_includes_confirmed_field_value(self) -> None:
        """확정 OCR 값(field_type: value)이 복약 안내 본문에 반영된다."""
        clinic = await make_clinic()
        staff = await make_staff(clinic, "staff01", ["staff"])
        visit = await make_visit(clinic)
        await attach_confirmed_ocr(visit, staff.staff_id)  # DIAGNOSIS: PCOS

        async with self.client() as client:
            response = await client.post(f"{BASE}/{visit.visit_id}/guide/generate", headers=await self.sign_in(staff))

        medication = next(s for s in response.json()["sections"] if s["key"] == GuideSectionKey.MEDICATION)
        assert "DIAGNOSIS" in medication["body"]
        assert "PCOS" in medication["body"]


class TestGenerateDuplicateIsRefused(GenerateGuideTestCase):
    """같은 진료에 안내를 두 번 만들 수 없다."""

    async def test_second_generate_returns_409(self) -> None:
        clinic = await make_clinic()
        staff = await make_staff(clinic, "staff01", ["staff"])
        visit = await make_visit(clinic)
        await attach_confirmed_ocr(visit, staff.staff_id)

        async with self.client() as client:
            headers = await self.sign_in(staff)
            first = await client.post(f"{BASE}/{visit.visit_id}/guide/generate", headers=headers)
            second = await client.post(f"{BASE}/{visit.visit_id}/guide/generate", headers=headers)

        assert first.status_code == 201
        assert second.status_code == 409
        assert second.json()["code"] == "GUIDE_ALREADY_EXISTS"


class TestGenerateRoleGuard(GenerateGuideTestCase):
    """generate()의 역할 가드 — GUIDE_DRAFT 는 staff·doctor 에게만 열린다."""

    async def test_admin_only_is_blocked(self) -> None:
        """admin 단독 계정은 안내를 생성할 수 없다."""
        clinic = await make_clinic()
        admin = await make_staff(clinic, "admin01", ["admin"])
        visit = await make_visit(clinic)
        await attach_confirmed_ocr(visit, admin.staff_id)

        async with self.client() as client:
            response = await client.post(f"{BASE}/{visit.visit_id}/guide/generate", headers=await self.sign_in(admin))

        assert response.status_code == 403
        assert response.json()["code"] == "FORBIDDEN"

    async def test_doctor_can_generate(self) -> None:
        """doctor 역할 단독도 안내를 생성할 수 있다."""
        clinic = await make_clinic()
        doctor = await make_staff(clinic, "doctor01", ["doctor"])
        visit = await make_visit(clinic)
        await attach_confirmed_ocr(visit, doctor.staff_id)

        async with self.client() as client:
            response = await client.post(f"{BASE}/{visit.visit_id}/guide/generate", headers=await self.sign_in(doctor))

        assert response.status_code == 201

    async def test_doctor_admin_combo_can_generate(self) -> None:
        """doctor+admin 조합은 doctor 역할을 포함하므로 생성할 수 있다."""
        clinic = await make_clinic()
        doctor_admin = await make_staff(clinic, "docadmin01", ["doctor", "admin"])
        visit = await make_visit(clinic)
        await attach_confirmed_ocr(visit, doctor_admin.staff_id)

        async with self.client() as client:
            response = await client.post(
                f"{BASE}/{visit.visit_id}/guide/generate", headers=await self.sign_in(doctor_admin)
            )

        assert response.status_code == 201


class TestGenerateHospitalIsolation(GenerateGuideTestCase):
    """타 병원 진료는 없는 것처럼 보인다 — 존재 여부를 감춘다(계약 §5)."""

    async def test_other_clinic_visit_returns_404(self) -> None:
        mine = await make_clinic("우리의원")
        theirs = await make_clinic("옆의원")
        visit = await make_visit(theirs)
        staff = await make_staff(mine, "staff01", ["staff"])

        async with self.client() as client:
            response = await client.post(f"{BASE}/{visit.visit_id}/guide/generate", headers=await self.sign_in(staff))

        assert response.status_code == 404


class TestGenerateThenApproveEndToEnd(GenerateGuideTestCase):
    """확정 OCR → 안내 생성 → 의사 승인 종단 흐름 — KEY-150 완료 조건."""

    async def test_generate_then_doctor_approves(self) -> None:
        clinic = await make_clinic()
        staff = await make_staff(clinic, "staff01", ["staff"])
        doctor = await make_staff(clinic, "doctor01", ["doctor"])
        visit = await make_visit(clinic)
        await attach_confirmed_ocr(visit, staff.staff_id)

        async with self.client() as client:
            gen = await client.post(f"{BASE}/{visit.visit_id}/guide/generate", headers=await self.sign_in(staff))
            approve = await client.post(f"{BASE}/{visit.visit_id}/guide/approve", headers=await self.sign_in(doctor))

        assert gen.status_code == 201
        assert gen.json()["status"] == GuideStatus.APPROVAL_PENDING
        assert approve.status_code == 200
        assert approve.json()["status"] == GuideStatus.SCHEDULED_TO_SEND

    async def test_staff_cannot_approve_after_generate(self) -> None:
        """생성 후에도 승인은 의사만 — 스탭 단독 승인 차단(KEY-150 완료 조건)."""
        clinic = await make_clinic()
        staff = await make_staff(clinic, "staff01", ["staff"])
        visit = await make_visit(clinic)
        await attach_confirmed_ocr(visit, staff.staff_id)

        async with self.client() as client:
            headers = await self.sign_in(staff)
            await client.post(f"{BASE}/{visit.visit_id}/guide/generate", headers=headers)
            approve = await client.post(f"{BASE}/{visit.visit_id}/guide/approve", headers=headers)

        assert approve.status_code == 403

    async def test_patient_access_blocked_before_approval(self) -> None:
        """승인 전 안내는 APPROVAL_PENDING 상태다 — 환자 조회 게이트가 이 상태를 본다."""
        clinic = await make_clinic()
        staff = await make_staff(clinic, "staff01", ["staff"])
        visit = await make_visit(clinic)
        await attach_confirmed_ocr(visit, staff.staff_id)

        async with self.client() as client:
            gen = await client.post(f"{BASE}/{visit.visit_id}/guide/generate", headers=await self.sign_in(staff))

        from app.models.visits import GuideDocument

        saved = await GuideDocument.get(visit_id=visit.visit_id)
        assert gen.json()["status"] == GuideStatus.APPROVAL_PENDING
        assert saved.approved_at is None, "승인 전에는 approved_at 이 비어 있어야 한다"
