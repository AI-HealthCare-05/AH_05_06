"""확정 OCR → 고정 안내 생성 연결 — KEY-150.

이 검사가 보려는 것은 **생성 게이트**다.
  · OCR 확정 전에는 안내를 만들 수 없다
  · 확정 후에는 승인 대기 안내 한 건이 만들어진다
  · emergency 섹션만 locked=True — 식약처 근거 응급 문장 (caution 은 고칠 수 있다)
  · 생성 후 승인은 의사만 할 수 있다 (기존 규칙 유지)
"""

from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient
from tortoise.contrib.test import TestCase

from app.core.redis_client import get_redis
from app.core.utils.security import hash_password
from app.main import app
from app.models.ocr import OcrField, OcrJob, OcrJobStatus, OcrResult  # noqa: F401 (OcrResult used in test setup)
from app.models.patients import Patient
from app.models.staffs import Hospital, Staff
from app.models.visits import GuideSectionKey, GuideStatus, Visit
from app.services.staff_auth import StaffSessionService
from app.tests.fakes import FakeRedis
from app.tests.ocr_fixture import complete_ocr

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
    """visit 에 완료·확정된 판독 한 건을 붙인다 — W1 fixture.

    만드는 일은 `app/tests/ocr_fixture.py` 가 한다. 예전에는 여기서 손으로
    만들어 운영의 완료 경로와 모양이 조금 달랐다 (KEY-172).
    """
    done = await complete_ocr(
        hospital_id=visit.hospital_id,
        visit_id=visit.visit_id,
        job_id=f"syn-gen-{visit.visit_id}",
        requested_by=staff_id,
        confirmed_by=staff_id,
    )
    return await OcrField.get(ocr_field_id=done.field_id)


class GenerateGuideTestCase(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.redis = FakeRedis()
        app.dependency_overrides[get_redis] = lambda: self.redis

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        super().tearDown()

    async def sign_in(self, staff: Staff) -> dict[str, str]:
        access, _ = await StaffSessionService(self.redis).start(staff)  # type: ignore[arg-type]
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


class TestGenerateCreatesStaffReviewGuide(GenerateGuideTestCase):
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
        # **만들면 스탭 확인부터다** (와이어프레임 S1-11). 전에는 바로
        # APPROVAL_PENDING 이라 만들자마자 원장님 목록에 떴다 — 「스탭이
        # 넘기지 않으면 원장님 목록에 뜨지 않는다」가 지켜지지 않았다.
        assert body["status"] == GuideStatus.STAFF_REVIEW
        assert body["visit_id"] == visit.visit_id

    async def test_all_five_sections_are_created_in_order(self) -> None:
        clinic = await make_clinic()
        staff = await make_staff(clinic, "staff01", ["staff"])
        visit = await make_visit(clinic)
        await attach_confirmed_ocr(visit, staff.staff_id)

        async with self.client() as client:
            response = await client.post(f"{BASE}/{visit.visit_id}/guide/generate", headers=await self.sign_in(staff))

        sections = response.json()["sections"]
        assert [s["key"] for s in sections] == [
            GuideSectionKey.MEDICATION,
            GuideSectionKey.CAUTION,
            GuideSectionKey.EMERGENCY,
            GuideSectionKey.LIFE,
            GuideSectionKey.MESSAGES,
        ], "차례까지 계약이다 — 응답 순서가 곧 환자 화면의 차례다(P2·P3·P4)"

    async def test_only_emergency_is_locked(self) -> None:
        """**응급 갈래만** 잠긴다 — caution 을 포함해 나머지는 고칠 수 있다.

        KEY-161. 예전에는 `caution` 이 잠겨 있었다. 응급 문장을 지키려던
        것인데, 그러면 원장님이 환자에 맞춰 고쳐야 할 일반 주의 문구까지
        함께 잠긴다(와이어프레임 D1-2 — 「🚨 응급 문장만 수정 불가」).

        `caution` 이 풀렸는지를 함께 재는 것이 요점이다. `emergency` 가
        잠긴 것만 보면, 실수로 둘 다 잠가 둔 코드도 통과한다.
        """
        clinic = await make_clinic()
        staff = await make_staff(clinic, "staff01", ["staff"])
        visit = await make_visit(clinic)
        await attach_confirmed_ocr(visit, staff.staff_id)

        async with self.client() as client:
            response = await client.post(f"{BASE}/{visit.visit_id}/guide/generate", headers=await self.sign_in(staff))

        sections = {s["key"]: s for s in response.json()["sections"]}
        assert sections[GuideSectionKey.EMERGENCY]["locked"] is True
        assert sections[GuideSectionKey.CAUTION]["locked"] is False, (
            "일반 주의 문구가 잠겼다 — KEY-161 이 풀려던 바로 그 자리다"
        )
        assert sections[GuideSectionKey.MEDICATION]["locked"] is False
        assert sections[GuideSectionKey.LIFE]["locked"] is False
        assert sections[GuideSectionKey.MESSAGES]["locked"] is False

    async def test_medication_body_includes_confirmed_field_value(self) -> None:
        """확정 OCR 값(field_type: value)이 복약 안내 본문에 반영된다."""
        clinic = await make_clinic()
        staff = await make_staff(clinic, "staff01", ["staff"])
        visit = await make_visit(clinic)
        field = await attach_confirmed_ocr(visit, staff.staff_id)

        async with self.client() as client:
            response = await client.post(f"{BASE}/{visit.visit_id}/guide/generate", headers=await self.sign_in(staff))

        medication = next(s for s in response.json()["sections"] if s["key"] == GuideSectionKey.MEDICATION)
        # **픽스처가 넣은 값을 그대로 읽어 견준다.** 예전에는 `"PCOS"` 를 박아
        # 뒀는데, 그러면 픽스처가 값을 바꾸는 순간 이 검사가 「안내가 깨졌다」로
        # 잘못 운다. 재려는 것은 「확정된 값이 본문에 실린다」이지 그 값이
        # 무엇인지가 아니다 (KEY-172).
        assert field.field_type in medication["body"]
        assert field.extracted_value in medication["body"]


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
            staff_headers = await self.sign_in(staff)
            gen = await client.post(f"{BASE}/{visit.visit_id}/guide/generate", headers=staff_headers)
            # **스탭이 넘겨야 원장님 차례가 된다** — 이 한 단계가 없으면
            # 원장님이 아직 아무도 안 본 글을 받는다 (와이어프레임 S1-11).
            handoff = await client.post(f"{BASE}/{visit.visit_id}/guide/submit", headers=staff_headers)
            approve = await client.post(f"{BASE}/{visit.visit_id}/guide/approve", headers=await self.sign_in(doctor))

        assert gen.status_code == 201
        assert gen.json()["status"] == GuideStatus.STAFF_REVIEW
        assert handoff.status_code == 200
        assert handoff.json()["status"] == GuideStatus.APPROVAL_PENDING
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
        """승인 전 안내는 **승인된 상태가 아니다** — 환자 조회 게이트가 그것을 본다.

        만든 직후는 STAFF_REVIEW 다. 스탭이 넘기면 APPROVAL_PENDING 이 되고,
        의사가 승인해야 SCHEDULED_TO_SEND 가 된다. 어느 쪽이든 환자에게는
        아직 안 간다.
        """
        clinic = await make_clinic()
        staff = await make_staff(clinic, "staff01", ["staff"])
        visit = await make_visit(clinic)
        await attach_confirmed_ocr(visit, staff.staff_id)

        async with self.client() as client:
            gen = await client.post(f"{BASE}/{visit.visit_id}/guide/generate", headers=await self.sign_in(staff))

        from app.models.visits import GuideDocument

        saved = await GuideDocument.get(visit_id=visit.visit_id)
        assert gen.json()["status"] == GuideStatus.STAFF_REVIEW
        assert saved.approved_at is None, "승인 전에는 approved_at 이 비어 있어야 한다"


class TestGenerateGateLatestJob(GenerateGuideTestCase):
    """가장 최근 job 기준 게이트 — AC5 (KEY-226)."""

    async def test_new_unconfirmed_job_blocks_generation(self) -> None:
        """이전 job이 확정돼 있어도 더 최신 미확정 job이 있으면 422로 막힌다."""
        clinic = await make_clinic()
        staff = await make_staff(clinic, "staff01", ["staff"])
        visit = await make_visit(clinic)

        # 첫 번째 job — 완료·확정
        await attach_confirmed_ocr(visit, staff.staff_id)

        # 두 번째 job — 완료됐지만 미확정
        second_job = await OcrJob.create(
            ocr_job_id=f"syn-new-unconf-{visit.visit_id}",
            hospital_id=clinic.hospital_id,
            visit_id=visit.visit_id,
            requested_by=staff.staff_id,
            status=OcrJobStatus.COMPLETED,
        )
        second_result = await OcrResult.create(ocr_job=second_job, model_name="synthetic-fixture")
        await OcrField.create(
            ocr_result=second_result,
            field_type="DIAGNOSIS",
            extracted_value="자궁내막증",
            is_confirmed=False,
        )

        async with self.client() as client:
            response = await client.post(f"{BASE}/{visit.visit_id}/guide/generate", headers=await self.sign_in(staff))

        assert response.status_code == 422
        assert response.json()["code"] == "OCR_NOT_CONFIRMED"

    async def test_excluded_job_is_skipped_and_previous_confirmed_passes(self) -> None:
        """최신 job을 제외 처리하면 이전 확정 job 기준으로 게이트가 통과된다."""
        clinic = await make_clinic()
        staff = await make_staff(clinic, "staff01", ["staff"])
        visit = await make_visit(clinic)

        # 첫 번째 job — 완료·확정
        await attach_confirmed_ocr(visit, staff.staff_id)

        # 두 번째 job — 잘못 올린 문서, 제외 처리
        bad_job = await OcrJob.create(
            ocr_job_id=f"syn-excluded-{visit.visit_id}",
            hospital_id=clinic.hospital_id,
            visit_id=visit.visit_id,
            requested_by=staff.staff_id,
            status=OcrJobStatus.COMPLETED,
            excluded_from_guide=True,
        )
        bad_result = await OcrResult.create(ocr_job=bad_job, model_name="synthetic-fixture")
        await OcrField.create(
            ocr_result=bad_result,
            field_type="DIAGNOSIS",
            extracted_value="잘못된 문서",
            is_confirmed=False,
        )

        async with self.client() as client:
            response = await client.post(f"{BASE}/{visit.visit_id}/guide/generate", headers=await self.sign_in(staff))

        assert response.status_code == 201
