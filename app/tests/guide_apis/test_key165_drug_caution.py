"""처방 세트별 주의·응급 문구와 근거 버전 관리 — KEY-165.

D-1  정상 생성: 승인 문구 사용 + drug_caution_content_id 기록
D-2  미등록·미승인·근거 누락: 범용 폴백 사용
D-3  emergency 수정 차단 회귀: DB 콘텐츠로 채운 경우에도 locked 유지
D-4  버전 불변성: 새 버전 승인 후 기존 GuideSection 본문·ID 변경 없음
D-5  approved_key 경합: DB 유니크 제약이 승인 중복을 차단함
"""

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient, Response
from tortoise.contrib.test import TestCase
from tortoise.exceptions import IntegrityError

from app.core.redis_client import get_redis
from app.core.utils.security import hash_password
from app.main import app
from app.models.catalog import ApprovalStatus, CautionSectionKey, DrugCautionContent, PrescriptionSet
from app.models.ocr import OcrField
from app.models.patients import Patient
from app.models.prescriptions import Prescription
from app.models.staffs import Hospital, Staff
from app.models.visits import GuideSection, GuideSectionKey, Visit
from app.services.drug_caution import DrugCautionService
from app.services.guide_defaults import CAUTION as _CAUTION_FALLBACK
from app.services.guide_defaults import EMERGENCY as _EMERGENCY_FALLBACK
from app.services.staff_auth import StaffSessionService
from app.tests.fakes import FakeRedis
from app.tests.ocr_fixture import complete_ocr

BASE = "/api/v1/visits"

# ── 공통 헬퍼 ────────────────────────────────────────────────────────────────


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


async def make_visit(hospital: Hospital, set_name: str | None = None) -> Visit:
    patient = await Patient.create(
        hospital_id=hospital.hospital_id,
        hospital_patient_no="KEY165-01",
        name="합성환자",
        birth_date="1990-05-15",
        phone="01012345678",
        sms_consent=True,
    )
    visit = await Visit.create(
        hospital_id=hospital.hospital_id,
        patient=patient,
        visited_at=datetime(2026, 8, 26, 9, 0, tzinfo=UTC),
    )
    if set_name:
        await Prescription.create(visit=visit, prescription_set=set_name)
    return visit


async def attach_confirmed_ocr(visit: Visit, staff_id: int) -> OcrField:
    done = await complete_ocr(
        hospital_id=visit.hospital_id,
        visit_id=visit.visit_id,
        job_id=f"key165-{visit.visit_id}",
        requested_by=staff_id,
        confirmed_by=staff_id,
    )
    return await OcrField.get(ocr_field_id=done.field_id)


async def make_approved_content(
    set_name: str,
    section_key: CautionSectionKey,
    body: str,
    content_version: str = "2026-08-26",
) -> DrugCautionContent:
    """PrescriptionSet 과 승인된 DrugCautionContent 를 한 번에 만든다."""
    ps, _ = await PrescriptionSet.get_or_create(name=set_name)
    return await DrugCautionContent.create(
        prescription_set=ps,
        section_key=section_key,
        body=body,
        source_name="의약품안전나라 제품 허가사항",
        source_org="식품의약품안전처",
        source_url="https://nedrug.mfds.go.kr/TEST-ONLY/test",
        verified_at="2026-08-25",
        content_version=content_version,
        source_grade="A",
        approval_status=ApprovalStatus.APPROVED,
        approved_key=f"{ps.prescription_set_id}:{section_key.value}",
    )


async def make_draft_content(
    set_name: str,
    section_key: CautionSectionKey,
    body: str = "[합성 미승인]",
) -> DrugCautionContent:
    """승인되지 않은(DRAFT) DrugCautionContent 를 만든다."""
    ps, _ = await PrescriptionSet.get_or_create(name=set_name)
    return await DrugCautionContent.create(
        prescription_set=ps,
        section_key=section_key,
        body=body,
        source_name="의약품안전나라 제품 허가사항",
        source_org="식품의약품안전처",
        source_url="https://nedrug.mfds.go.kr/TEST-ONLY/draft",
        verified_at="2026-08-25",
        content_version="2026-08-26",
        source_grade="A",
        approval_status=ApprovalStatus.DRAFT,
        approved_key=None,
    )


# ── TestCase 베이스 ───────────────────────────────────────────────────────────


class DrugCautionTestCase(TestCase):
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

    async def generate(self, visit: Visit, staff: Staff) -> Response:
        async with self.client() as client:
            response = await client.post(
                f"{BASE}/{visit.visit_id}/guide/generate",
                headers=await self.sign_in(staff),
            )
        return response

    async def sections_from_db(self, visit_id: int) -> dict[GuideSectionKey, GuideSection]:
        sections = await GuideSection.filter(guide_document__visit_id=visit_id).all()
        return {s.section_key: s for s in sections}


# ── D-1: 정상 생성 ────────────────────────────────────────────────────────────


class TestGenerateUsesApprovedContent(DrugCautionTestCase):
    """D-1: 승인된 문구가 있으면 그것을 caution·emergency 에 사용한다."""

    async def test_caution_body_uses_approved_content(self) -> None:
        """승인 caution 문구가 GuideSection.generated_body 에 복사된다."""
        clinic = await make_clinic()
        staff = await make_staff(clinic, "staff01", ["staff"])
        caution = await make_approved_content(
            "자궁내막증 · 비잔 (계속)", CautionSectionKey.CAUTION, "[합성 세트별 주의 문구]"
        )
        await make_approved_content("자궁내막증 · 비잔 (계속)", CautionSectionKey.EMERGENCY, "[합성 세트별 응급 문구]")
        visit = await make_visit(clinic, set_name="자궁내막증 · 비잔 (계속)")
        await attach_confirmed_ocr(visit, staff.staff_id)

        resp = await self.generate(visit, staff)

        assert resp.status_code == 201
        sections = {s["key"]: s for s in resp.json()["sections"]}
        assert sections[GuideSectionKey.CAUTION]["body"] == caution.body

    async def test_emergency_body_uses_approved_content(self) -> None:
        """승인 emergency 문구가 GuideSection.generated_body 에 복사된다."""
        clinic = await make_clinic()
        staff = await make_staff(clinic, "staff01", ["staff"])
        await make_approved_content("자궁내막증 · 비잔 (계속)", CautionSectionKey.CAUTION, "[합성 세트별 주의 문구]")
        emergency = await make_approved_content(
            "자궁내막증 · 비잔 (계속)", CautionSectionKey.EMERGENCY, "[합성 세트별 응급 문구]"
        )
        visit = await make_visit(clinic, set_name="자궁내막증 · 비잔 (계속)")
        await attach_confirmed_ocr(visit, staff.staff_id)

        resp = await self.generate(visit, staff)

        assert resp.status_code == 201
        sections = {s["key"]: s for s in resp.json()["sections"]}
        assert sections[GuideSectionKey.EMERGENCY]["body"] == emergency.body

    async def test_drug_caution_content_id_is_recorded(self) -> None:
        """생성 후 GuideSection.drug_caution_content_id 에 사용한 버전 ID 가 기록된다(KEY-180 §6)."""
        clinic = await make_clinic()
        staff = await make_staff(clinic, "staff01", ["staff"])
        caution = await make_approved_content("자궁내막증 · 비잔 (계속)", CautionSectionKey.CAUTION, "[합성 주의]")
        emergency = await make_approved_content("자궁내막증 · 비잔 (계속)", CautionSectionKey.EMERGENCY, "[합성 응급]")
        visit = await make_visit(clinic, set_name="자궁내막증 · 비잔 (계속)")
        await attach_confirmed_ocr(visit, staff.staff_id)

        resp = await self.generate(visit, staff)
        assert resp.status_code == 201

        db = await self.sections_from_db(visit.visit_id)
        assert db[GuideSectionKey.CAUTION].drug_caution_content_id == caution.drug_caution_content_id
        assert db[GuideSectionKey.EMERGENCY].drug_caution_content_id == emergency.drug_caution_content_id

    async def test_a_section_from_the_catalog_carries_its_evidence(self) -> None:
        """**근거는 글을 따라간다** — 카탈로그에서 온 절은 그 판을 가리킨다.

        예전 이 검사는 「medication·life 는 `drug_caution_content_id` 가 NULL
        이다」를 불변식으로 적어 두었다. 그때는 주의·응급만 카탈로그에서 왔기
        때문이다. 승인 정본이 복약지도·생활지도까지 덮으면서(KEY-265) 그 말은
        사실이 아니게 됐는데, **검사는 그 문구를 안 심어서 우연히 통과했다** —
        규칙으로 읽으면 오해를 부르고 새 동작은 아무도 안 재고 있었다
        (이희진 님 `#214` ④).

        지금 재는 것은 「어느 갈래냐」가 아니라 **「그 글이 어디서 왔느냐」**다.
        """
        clinic = await make_clinic()
        staff = await make_staff(clinic, "staff01", ["staff"])
        picked = {}
        for section in (
            CautionSectionKey.MEDICATION,
            CautionSectionKey.CAUTION,
            CautionSectionKey.LIFE,
        ):
            picked[section] = await make_approved_content(
                "자궁내막증 · 비잔 (계속)", section, f"[합성] {section.value} 승인 원본"
            )
        visit = await make_visit(clinic, set_name="자궁내막증 · 비잔 (계속)")
        await attach_confirmed_ocr(visit, staff.staff_id)

        resp = await self.generate(visit, staff)
        assert resp.status_code == 201

        db = await self.sections_from_db(visit.visit_id)
        pairs = (
            (GuideSectionKey.MEDICATION, CautionSectionKey.MEDICATION),
            (GuideSectionKey.CAUTION, CautionSectionKey.CAUTION),
            (GuideSectionKey.LIFE, CautionSectionKey.LIFE),
        )
        for guide_key, caution_key in pairs:
            assert db[guide_key].drug_caution_content_id == picked[caution_key].drug_caution_content_id, (
                f"{guide_key} 가 제 근거를 안 가리킨다"
            )

    async def test_a_section_that_fell_back_carries_no_evidence(self) -> None:
        """**범용 문구로 내려간 절은 가리킬 근거가 없다** — NULL 이 그 뜻이다.

        주의만 승인해 두고 복약지도·생활지도는 비워 둔다. 그 둘은
        `guide_defaults` 에서 오므로 근거가 없어야 한다. NULL 이 「카탈로그에서
        안 왔다」를 뜻한다는 것을 여기서 못박는다.
        """
        clinic = await make_clinic()
        staff = await make_staff(clinic, "staff01", ["staff"])
        await make_approved_content("자궁내막증 · 비잔 (계속)", CautionSectionKey.CAUTION, "[합성] 주의만")
        visit = await make_visit(clinic, set_name="자궁내막증 · 비잔 (계속)")
        await attach_confirmed_ocr(visit, staff.staff_id)

        resp = await self.generate(visit, staff)
        assert resp.status_code == 201

        db = await self.sections_from_db(visit.visit_id)
        assert db[GuideSectionKey.CAUTION].drug_caution_content_id is not None, "승인해 둔 절이 근거를 잃었다"
        for key in (GuideSectionKey.MEDICATION, GuideSectionKey.LIFE, GuideSectionKey.MESSAGES):
            assert db[key].drug_caution_content_id is None, f"{key} 는 범용 문구에서 왔는데 근거를 달았다"


# ── D-2: 미등록·미승인·근거 누락 → 폴백 ──────────────────────────────────────


class TestGenerateFallsBackWhenNoContent(DrugCautionTestCase):
    """D-2: 승인 문구가 없으면 범용 폴백을 쓰고 생성 자체를 막지 않는다(KEY-180 §4)."""

    async def test_unregistered_set_uses_caution_fallback(self) -> None:
        """PrescriptionSet 에 없는 세트 이름 → caution 폴백, content_id=None."""
        clinic = await make_clinic()
        staff = await make_staff(clinic, "staff01", ["staff"])
        visit = await make_visit(clinic, set_name="미등록세트XYZ")
        await attach_confirmed_ocr(visit, staff.staff_id)

        resp = await self.generate(visit, staff)

        assert resp.status_code == 201
        db = await self.sections_from_db(visit.visit_id)
        assert db[GuideSectionKey.CAUTION].generated_body == _CAUTION_FALLBACK
        assert db[GuideSectionKey.CAUTION].drug_caution_content_id is None

    async def test_unregistered_set_uses_emergency_fallback(self) -> None:
        """PrescriptionSet 에 없는 세트 이름 → emergency 폴백, content_id=None."""
        clinic = await make_clinic()
        staff = await make_staff(clinic, "staff01", ["staff"])
        visit = await make_visit(clinic, set_name="미등록세트XYZ")
        await attach_confirmed_ocr(visit, staff.staff_id)

        resp = await self.generate(visit, staff)

        assert resp.status_code == 201
        db = await self.sections_from_db(visit.visit_id)
        assert db[GuideSectionKey.EMERGENCY].generated_body == _EMERGENCY_FALLBACK
        assert db[GuideSectionKey.EMERGENCY].drug_caution_content_id is None

    async def test_draft_only_content_uses_caution_fallback(self) -> None:
        """DRAFT 상태 문구만 있을 때 caution 은 폴백을 쓴다 — 미승인 차단(KEY-180 §4)."""
        clinic = await make_clinic()
        staff = await make_staff(clinic, "staff01", ["staff"])
        await make_draft_content("PCOS · 초진", CautionSectionKey.CAUTION, "[합성 미승인 주의]")
        visit = await make_visit(clinic, set_name="PCOS · 초진")
        await attach_confirmed_ocr(visit, staff.staff_id)

        resp = await self.generate(visit, staff)

        assert resp.status_code == 201
        db = await self.sections_from_db(visit.visit_id)
        assert db[GuideSectionKey.CAUTION].generated_body == _CAUTION_FALLBACK
        assert db[GuideSectionKey.CAUTION].drug_caution_content_id is None

    async def test_emergency_only_approved_uses_caution_fallback(self) -> None:
        """emergency 만 승인되고 caution 이 없을 때 caution 은 폴백을 쓴다.

        예전에는 seed 픽스처에 이 모양의 세트가 있어 그것을 재현했다.
        KEY-262 로 대표 처방이 넷이 되면서 seed 는 고르게 완비됐고, 이 테스트가
        쓰는 상태는 **여기서 직접 만든다.** 세트 이름은 그때의 이름을 남겨 둔
        것뿐이라, 지금은 카탈로그에 없는 이름이다 — 그래서 오히려 안전하다.
        """
        clinic = await make_clinic()
        staff = await make_staff(clinic, "staff01", ["staff"])
        emergency = await make_approved_content(
            "PCOS · 초진 (야즈 불가)", CautionSectionKey.EMERGENCY, "[합성 야즈불가 응급]"
        )
        visit = await make_visit(clinic, set_name="PCOS · 초진 (야즈 불가)")
        await attach_confirmed_ocr(visit, staff.staff_id)

        resp = await self.generate(visit, staff)

        assert resp.status_code == 201
        db = await self.sections_from_db(visit.visit_id)
        # caution: 승인 문구 없음 → 폴백
        assert db[GuideSectionKey.CAUTION].generated_body == _CAUTION_FALLBACK
        assert db[GuideSectionKey.CAUTION].drug_caution_content_id is None
        # emergency: 승인 문구 있음 → 사용
        assert db[GuideSectionKey.EMERGENCY].generated_body == emergency.body
        assert db[GuideSectionKey.EMERGENCY].drug_caution_content_id == emergency.drug_caution_content_id

    async def test_no_prescription_uses_both_fallbacks(self) -> None:
        """처방 자체가 없으면 caution·emergency 모두 폴백을 사용한다."""
        clinic = await make_clinic()
        staff = await make_staff(clinic, "staff01", ["staff"])
        visit = await make_visit(clinic, set_name=None)  # 처방 없음
        await attach_confirmed_ocr(visit, staff.staff_id)

        resp = await self.generate(visit, staff)

        assert resp.status_code == 201
        db = await self.sections_from_db(visit.visit_id)
        assert db[GuideSectionKey.CAUTION].generated_body == _CAUTION_FALLBACK
        assert db[GuideSectionKey.EMERGENCY].generated_body == _EMERGENCY_FALLBACK

    async def test_grade_b_approved_content_uses_fallback(self) -> None:
        """B등급 APPROVED 문구는 단독 근거 불가 — 폴백을 사용한다(KEY-180 §2)."""
        clinic = await make_clinic()
        staff = await make_staff(clinic, "staff01", ["staff"])
        ps, _ = await PrescriptionSet.get_or_create(name="테스트세트-B등급")
        await DrugCautionContent.create(
            prescription_set=ps,
            section_key=CautionSectionKey.CAUTION,
            body="[합성 B등급 주의]",
            source_name="학술지",
            source_org="학회",
            source_url="https://nedrug.mfds.go.kr/TEST-ONLY/b-grade",
            verified_at="2026-08-25",
            content_version="v1",
            source_grade="B",
            approval_status=ApprovalStatus.APPROVED,
            approved_key=f"{ps.prescription_set_id}:caution",
        )
        visit = await make_visit(clinic, set_name="테스트세트-B등급")
        await attach_confirmed_ocr(visit, staff.staff_id)

        resp = await self.generate(visit, staff)

        assert resp.status_code == 201
        db = await self.sections_from_db(visit.visit_id)
        assert db[GuideSectionKey.CAUTION].generated_body == _CAUTION_FALLBACK
        assert db[GuideSectionKey.CAUTION].drug_caution_content_id is None

    async def test_grade_c_approved_content_uses_fallback(self) -> None:
        """C등급 APPROVED 문구는 이번 범위 사용 불가 — 폴백을 사용한다(KEY-180 §2)."""
        clinic = await make_clinic()
        staff = await make_staff(clinic, "staff01", ["staff"])
        ps, _ = await PrescriptionSet.get_or_create(name="테스트세트-C등급")
        await DrugCautionContent.create(
            prescription_set=ps,
            section_key=CautionSectionKey.EMERGENCY,
            body="[합성 C등급 응급]",
            source_name="비공개자료",
            source_org="미상",
            source_url="https://nedrug.mfds.go.kr/TEST-ONLY/c-grade",
            verified_at="2026-08-25",
            content_version="v1",
            source_grade="C",
            approval_status=ApprovalStatus.APPROVED,
            approved_key=f"{ps.prescription_set_id}:emergency",
        )
        visit = await make_visit(clinic, set_name="테스트세트-C등급")
        await attach_confirmed_ocr(visit, staff.staff_id)

        resp = await self.generate(visit, staff)

        assert resp.status_code == 201
        db = await self.sections_from_db(visit.visit_id)
        assert db[GuideSectionKey.EMERGENCY].generated_body == _EMERGENCY_FALLBACK
        assert db[GuideSectionKey.EMERGENCY].drug_caution_content_id is None

    async def test_approved_with_null_key_uses_fallback(self) -> None:
        """APPROVED 상태여도 approved_key 가 NULL 이면 조회되지 않아 폴백을 사용한다.

        approved_key 로 조회하므로 NULL 행은 결코 반환되지 않는다(KEY-180 §3).
        이 검사가 있어야 approved_key → approval_status 로 되돌리는 실수를 CI 가 잡는다.
        """
        clinic = await make_clinic()
        staff = await make_staff(clinic, "staff01", ["staff"])
        ps, _ = await PrescriptionSet.get_or_create(name="테스트세트-키없음")
        await DrugCautionContent.create(
            prescription_set=ps,
            section_key=CautionSectionKey.CAUTION,
            body="[합성 키없는 승인]",
            source_name="의약품안전나라 제품 허가사항",
            source_org="식품의약품안전처",
            source_url="https://nedrug.mfds.go.kr/TEST-ONLY/no-key",
            verified_at="2026-08-25",
            content_version="v1",
            source_grade="A",
            approval_status=ApprovalStatus.APPROVED,
            approved_key=None,  # approved_key 없음 — 조회 불가여야 한다
        )
        visit = await make_visit(clinic, set_name="테스트세트-키없음")
        await attach_confirmed_ocr(visit, staff.staff_id)

        resp = await self.generate(visit, staff)

        assert resp.status_code == 201
        db = await self.sections_from_db(visit.visit_id)
        assert db[GuideSectionKey.CAUTION].generated_body == _CAUTION_FALLBACK
        assert db[GuideSectionKey.CAUTION].drug_caution_content_id is None

    async def test_empty_source_metadata_uses_fallback(self) -> None:
        """근거 메타데이터가 비어 있으면 폴백을 사용한다(KEY-180 §4)."""
        clinic = await make_clinic()
        staff = await make_staff(clinic, "staff01", ["staff"])
        ps, _ = await PrescriptionSet.get_or_create(name="테스트세트-빈근거")
        await DrugCautionContent.create(
            prescription_set=ps,
            section_key=CautionSectionKey.CAUTION,
            body="[합성 빈근거 주의]",
            source_name="",  # 빈 문자열
            source_org="",
            source_url="",
            verified_at="2026-08-25",
            content_version="",
            source_grade="A",
            approval_status=ApprovalStatus.APPROVED,
            approved_key=f"{ps.prescription_set_id}:caution",
        )
        visit = await make_visit(clinic, set_name="테스트세트-빈근거")
        await attach_confirmed_ocr(visit, staff.staff_id)

        resp = await self.generate(visit, staff)

        assert resp.status_code == 201
        db = await self.sections_from_db(visit.visit_id)
        assert db[GuideSectionKey.CAUTION].generated_body == _CAUTION_FALLBACK
        assert db[GuideSectionKey.CAUTION].drug_caution_content_id is None


# ── D-3: emergency 수정 차단 회귀 ────────────────────────────────────────────


class TestEmergencyEditLockWithDbContent(DrugCautionTestCase):
    """D-3: DB 콘텐츠로 채운 emergency 섹션도 locked=True 이고 수정이 차단된다."""

    async def test_emergency_from_db_content_is_locked(self) -> None:
        """DB 승인 문구로 생성된 emergency 는 API 응답에서 locked=True 다."""
        clinic = await make_clinic()
        staff = await make_staff(clinic, "staff01", ["staff"])
        await make_approved_content("자궁내막증 · 비잔 (처음)", CautionSectionKey.CAUTION, "[합성]")
        await make_approved_content("자궁내막증 · 비잔 (처음)", CautionSectionKey.EMERGENCY, "[합성 응급]")
        visit = await make_visit(clinic, set_name="자궁내막증 · 비잔 (처음)")
        await attach_confirmed_ocr(visit, staff.staff_id)

        resp = await self.generate(visit, staff)
        sections = {s["key"]: s for s in resp.json()["sections"]}

        assert sections[GuideSectionKey.EMERGENCY]["locked"] is True
        assert sections[GuideSectionKey.CAUTION]["locked"] is False

    async def test_editing_db_content_emergency_is_refused(self) -> None:
        """DB 승인 문구로 생성된 emergency 섹션 수정 시도 → 409 SECTION_LOCKED."""
        clinic = await make_clinic()
        staff = await make_staff(clinic, "staff01", ["staff"])
        doctor = await make_staff(clinic, "doctor01", ["doctor"])
        await make_approved_content("자궁내막증 · 비잔 (처음)", CautionSectionKey.CAUTION, "[합성]")
        await make_approved_content("자궁내막증 · 비잔 (처음)", CautionSectionKey.EMERGENCY, "[합성 응급]")
        visit = await make_visit(clinic, set_name="자궁내막증 · 비잔 (처음)")
        await attach_confirmed_ocr(visit, staff.staff_id)
        await self.generate(visit, staff)

        async with self.client() as client:
            response = await client.patch(
                f"{BASE}/{visit.visit_id}/guide/sections/emergency",
                json={"body": "임의로 바꾸는 시도"},
                headers=await self.sign_in(doctor),
            )

        assert response.status_code == 409
        assert response.json()["code"] == "SECTION_LOCKED"


# ── D-4: 버전 불변성 ──────────────────────────────────────────────────────────


class TestGeneratedBodyIsImmutableAfterApproveVersion(DrugCautionTestCase):
    """D-4: 새 버전 승인 후에도 기존 GuideSection 본문과 content_id 는 바뀌지 않는다(KEY-180 §6)."""

    async def test_existing_guide_section_body_unchanged(self) -> None:
        """approve_version 이후 기존 GuideSection.generated_body 는 그대로다."""
        clinic = await make_clinic()
        staff = await make_staff(clinic, "staff01", ["staff"])
        old_caution = await make_approved_content(
            "자궁내막증 · 비잔 (계속)", CautionSectionKey.CAUTION, "[합성 구버전 주의]", "v1"
        )
        await make_approved_content("자궁내막증 · 비잔 (계속)", CautionSectionKey.EMERGENCY, "[합성]")
        visit = await make_visit(clinic, set_name="자궁내막증 · 비잔 (계속)")
        await attach_confirmed_ocr(visit, staff.staff_id)
        await self.generate(visit, staff)

        # 신규 버전 등록 후 승인
        ps = await PrescriptionSet.get(name="자궁내막증 · 비잔 (계속)")
        new_caution = await DrugCautionContent.create(
            prescription_set=ps,
            section_key=CautionSectionKey.CAUTION,
            body="[합성 신버전 주의]",
            source_name="의약품안전나라 제품 허가사항",
            source_org="식품의약품안전처",
            source_url="https://nedrug.mfds.go.kr/TEST-ONLY/v2",
            verified_at="2026-08-26",
            content_version="v2",
            source_grade="A",
            approval_status=ApprovalStatus.DRAFT,
            approved_key=None,
        )
        await DrugCautionService.approve_version(new_caution.drug_caution_content_id)

        # 기존 GuideSection 은 여전히 구버전 본문을 갖는다
        db = await self.sections_from_db(visit.visit_id)
        assert db[GuideSectionKey.CAUTION].generated_body == old_caution.body

    async def test_existing_content_id_unchanged_after_new_approval(self) -> None:
        """approve_version 이후 기존 GuideSection.drug_caution_content_id 는 그대로다."""
        clinic = await make_clinic()
        staff = await make_staff(clinic, "staff01", ["staff"])
        old_caution = await make_approved_content(
            "자궁내막증 · 비잔 (계속)", CautionSectionKey.CAUTION, "[합성 구버전]", "v1"
        )
        await make_approved_content("자궁내막증 · 비잔 (계속)", CautionSectionKey.EMERGENCY, "[합성]")
        visit = await make_visit(clinic, set_name="자궁내막증 · 비잔 (계속)")
        await attach_confirmed_ocr(visit, staff.staff_id)
        await self.generate(visit, staff)

        ps = await PrescriptionSet.get(name="자궁내막증 · 비잔 (계속)")
        new_caution = await DrugCautionContent.create(
            prescription_set=ps,
            section_key=CautionSectionKey.CAUTION,
            body="[합성 신버전]",
            source_name="의약품안전나라 제품 허가사항",
            source_org="식품의약품안전처",
            source_url="https://nedrug.mfds.go.kr/TEST-ONLY/v2",
            verified_at="2026-08-26",
            content_version="v2",
            source_grade="A",
            approval_status=ApprovalStatus.DRAFT,
            approved_key=None,
        )
        await DrugCautionService.approve_version(new_caution.drug_caution_content_id)

        db = await self.sections_from_db(visit.visit_id)
        assert db[GuideSectionKey.CAUTION].drug_caution_content_id == old_caution.drug_caution_content_id


# ── D-5: approved_key 경합 ────────────────────────────────────────────────────


class TestApprovedKeyUniquenessConstraint(DrugCautionTestCase):
    """D-5: DB 유니크 제약이 같은 approved_key 를 두 행에 동시에 허용하지 않는다."""

    async def test_duplicate_approved_key_on_two_rows_is_rejected_by_db(self) -> None:
        """같은 approved_key 를 두 행에 INSERT 하면 DB 유니크 제약이 거부한다."""
        ps = await PrescriptionSet.create(name="테스트세트")
        approved_key = f"{ps.prescription_set_id}:caution"

        await DrugCautionContent.create(
            prescription_set=ps,
            section_key=CautionSectionKey.CAUTION,
            body="[합성 첫째]",
            source_name="의약품안전나라 제품 허가사항",
            source_org="식품의약품안전처",
            source_url="https://nedrug.mfds.go.kr/TEST-ONLY/a",
            verified_at="2026-08-25",
            content_version="v1",
            source_grade="A",
            approval_status=ApprovalStatus.APPROVED,
            approved_key=approved_key,
        )

        with pytest.raises(IntegrityError):
            await DrugCautionContent.create(
                prescription_set=ps,
                section_key=CautionSectionKey.CAUTION,
                body="[합성 둘째]",
                source_name="의약품안전나라 제품 허가사항",
                source_org="식품의약품안전처",
                source_url="https://nedrug.mfds.go.kr/TEST-ONLY/b",
                verified_at="2026-08-25",
                content_version="v2",
                source_grade="A",
                approval_status=ApprovalStatus.APPROVED,
                approved_key=approved_key,  # 충돌
            )

    async def test_approve_version_deprecates_previous_and_approves_new(self) -> None:
        """approve_version 은 이전 버전을 DEPRECATED 로 바꾸고 새 버전을 APPROVED 로 올린다."""
        ps = await PrescriptionSet.create(name="테스트세트2")
        old = await DrugCautionContent.create(
            prescription_set=ps,
            section_key=CautionSectionKey.EMERGENCY,
            body="[합성 구버전]",
            source_name="의약품안전나라 제품 허가사항",
            source_org="식품의약품안전처",
            source_url="https://nedrug.mfds.go.kr/TEST-ONLY/old",
            verified_at="2026-08-25",
            content_version="v1",
            source_grade="A",
            approval_status=ApprovalStatus.APPROVED,
            approved_key=f"{ps.prescription_set_id}:emergency",
        )
        new = await DrugCautionContent.create(
            prescription_set=ps,
            section_key=CautionSectionKey.EMERGENCY,
            body="[합성 신버전]",
            source_name="의약품안전나라 제품 허가사항",
            source_org="식품의약품안전처",
            source_url="https://nedrug.mfds.go.kr/TEST-ONLY/new",
            verified_at="2026-08-26",
            content_version="v2",
            source_grade="A",
            approval_status=ApprovalStatus.DRAFT,
            approved_key=None,
        )

        await DrugCautionService.approve_version(new.drug_caution_content_id)

        await old.refresh_from_db()
        await new.refresh_from_db()
        assert old.approval_status == ApprovalStatus.DEPRECATED
        assert old.approved_key is None
        assert new.approval_status == ApprovalStatus.APPROVED
        assert new.approved_key == f"{ps.prescription_set_id}:emergency"

    async def test_approve_version_is_idempotent(self) -> None:
        """이미 APPROVED 인 행에 approve_version 을 호출해도 상태가 바뀌지 않는다."""
        ps = await PrescriptionSet.create(name="테스트세트3")
        content = await DrugCautionContent.create(
            prescription_set=ps,
            section_key=CautionSectionKey.CAUTION,
            body="[합성]",
            source_name="의약품안전나라 제품 허가사항",
            source_org="식품의약품안전처",
            source_url="https://nedrug.mfds.go.kr/TEST-ONLY/idem",
            verified_at="2026-08-25",
            content_version="v1",
            source_grade="A",
            approval_status=ApprovalStatus.APPROVED,
            approved_key=f"{ps.prescription_set_id}:caution",
        )

        result = await DrugCautionService.approve_version(content.drug_caution_content_id)

        assert result.approval_status == ApprovalStatus.APPROVED
        assert result.drug_caution_content_id == content.drug_caution_content_id
