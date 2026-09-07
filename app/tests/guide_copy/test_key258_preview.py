"""미리보기가 **실제로 나가는 글과 같다** — KEY-258.

D2-2 는 문구를 고칠 수 있게 해 놓고 **그 글이 안내문에 어떻게 나가는지 볼 길이
없었다.** 저장만 되고, 확인하려면 진료를 하나 열어 봐야 했다.

## 여기서 재는 것

인수조건 2 —「미리보기 내용이 실제 `GuideService.generate()` 결과와 일치한다」—
가 이 티켓의 값 전부다. 그리고 그것을 지키는 길은 원리상 하나뿐이다:
**두 쪽이 같은 함수를 부르는 것.**

그래서 여기서는 「지금 같은가」가 아니라 **두 경로를 실제로 돌려 맞대 본다.**
규칙이 갈리는 날 이 검사가 운다.

## 못 지키는 것을 분명히 적는다

설정 화면에는 **진료가 없다.** 그래서 둘을 모른다.

    약 목록      복약지도는 그 진료의 처방 행이 문장 위에 붙는다
    누구 문구냐   생성은 「의원 공통 위에 담당 원장님 것」을 덮는다

미리보기는 **처방 행이 없는 진료 · 의원 공통 기준**이다. 그것이 근사치가
아니라 실제로 도달하는 상태라는 것이 요점이다 — 화면도 그 범위를 적는다.
"""

from datetime import UTC, date, datetime

from httpx import ASGITransport, AsyncClient
from tortoise.contrib.test import TestCase

from app.core.redis_client import get_redis
from app.core.utils.security import hash_password
from app.main import app
from app.models.catalog import (
    ApprovalStatus,
    CautionSectionKey,
    DoctorGuideCopy,
    DrugCautionContent,
    PrescriptionSet,
    SourceGrade,
)
from app.models.ocr import OcrField, OcrJob, OcrJobStatus, OcrResult
from app.models.patients import Patient
from app.models.prescriptions import Prescription, PrescriptionItem
from app.models.staffs import Hospital, Staff
from app.models.visits import GuideSection, GuideSectionKey, Visit
from app.services import guide_defaults
from app.services.guides import GuideService
from app.services.staff_auth import StaffSessionService
from app.tests.fakes import FakeRedis
from app.tests.guide_copy.test_guide_copy import MINE, ORIGIN

SET_NAME = "자궁내막증 · 비잔 (계속)"


class PreviewTestCase(TestCase):
    """**부모 검사를 물려받지 않는다.** 헬퍼만 여기 다시 적는다.

    `GuideCopyTestCase` 를 상속하면 그쪽 검사 스무 건이 이 파일 이름으로 한 번
    더 돈다 — 같은 것을 두 번 재면 초록의 뜻이 흐려진다. 이 저장소의 선례도
    **클래스가 아니라 함수를 빌리는** 쪽이다.
    """

    def setUp(self) -> None:
        super().setUp()
        self.redis = FakeRedis()
        app.dependency_overrides[get_redis] = lambda: self.redis

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        super().tearDown()

    def client(self) -> AsyncClient:
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    async def headers(self, staff: Staff) -> dict[str, str]:
        access, _ = await StaffSessionService(self.redis).start(staff)  # type: ignore[arg-type]
        return {"Authorization": f"Bearer {access}"}

    async def a_set(self, name: str = "자궁내막증 · 비잔 (계속)") -> PrescriptionSet:
        return await PrescriptionSet.create(name=name)

    async def an_origin(
        self,
        row: PrescriptionSet,
        section: CautionSectionKey = CautionSectionKey.CAUTION,
        *,
        body: str = ORIGIN,
    ) -> DrugCautionContent:
        return await DrugCautionContent.create(
            prescription_set=row,
            section_key=section,
            body=body,
            source_name="합성 출처",
            source_org="합성 기관",
            source_url="https://example.invalid/synthetic",
            verified_at=date(2026, 1, 1),
            content_version="v1",
            source_grade=SourceGrade.A,
            approval_status=ApprovalStatus.APPROVED,
            approved_key=f"{row.prescription_set_id}:{section.value}",
        )

    async def a_staff(self, roles: list[str], login: str) -> Staff:
        clinic = await Hospital.create(name=f"의원 {login}")
        return await Staff.create(
            hospital=clinic,
            login_id=login,
            password_hash=hash_password("pw"),
            name="박연",
            roles=roles,
            must_change_password=False,
        )

    async def fetch(self, staff: Staff) -> dict:
        async with self.client() as client:
            response = await client.get("/api/v1/guide-copy", headers=await self.headers(staff))
        assert response.status_code == 200, response.text
        return response.json()

    async def save(self, staff: Staff, row: PrescriptionSet, body: str, section: str = "caution"):
        async with self.client() as client:
            return await client.put(
                f"/api/v1/guide-copy/{row.prescription_set_id}/{section}",
                headers=await self.headers(staff),
                json={"body": body},
            )

    async def sections_of(self, staff: Staff, row: PrescriptionSet) -> dict[str, dict]:
        page = await self.fetch(staff)
        for item in page["items"]:
            if item["prescription_set_id"] == row.prescription_set_id:
                return {part["section_key"]: part for part in item["sections"]}
        raise AssertionError("그 세트가 응답에 없다")

    async def test_the_preview_shows_the_doctors_wording(self) -> None:
        """**인수조건 ①** — 고치고 저장하면 미리보기가 그 문구로 갱신된다."""
        row = await self.a_set()
        await self.an_origin(row)
        staff = await self.a_staff(["doctor"], "key258-a")

        before = (await self.sections_of(staff, row))["caution"]
        assert before["preview"] == ORIGIN, "안 고쳤으면 원본이 나간다"

        saved = await self.save(staff, row, MINE)
        assert saved.status_code == 200, saved.text

        after = (await self.sections_of(staff, row))["caution"]
        assert after["preview"] == MINE, f"고친 글이 미리보기에 안 왔다 — {after['preview']!r}"

    async def test_the_saving_response_already_carries_it(self) -> None:
        """왕복이 공짜다 — 저장 응답이 곧 미리보기다.

        새 종점을 파면 화면이 저장 뒤 한 번 더 불러야 하고, 그 사이가 곧
        「저장은 됐는데 미리보기는 옛 글」인 구간이 된다.
        """
        row = await self.a_set()
        await self.an_origin(row)
        staff = await self.a_staff(["doctor"], "key258-b")

        saved = await self.save(staff, row, MINE)

        parts = {p["section_key"]: p for item in saved.json()["items"] for p in item["sections"]}
        assert parts["caution"]["preview"] == MINE

    async def test_without_an_approved_origin_the_default_wording_is_what_goes_out(self) -> None:
        """**폴백** — 승인 문구가 없으면 기본 문구가 나간다. 빈칸이 아니다."""
        row = await self.a_set()
        staff = await self.a_staff(["doctor"], "key258-c")

        parts = await self.sections_of(staff, row)

        assert parts["caution"]["preview"] == guide_defaults.CAUTION
        assert parts["life"]["preview"] == guide_defaults.LIFE

    async def test_the_emergency_line_never_takes_a_copy(self) -> None:
        """🚨 응급은 문구를 심어도 안 바뀐다 — KEY-150.

        화면은 그 갈래를 `editable=False` 로 잠그지만, **그 잠금이 풀리는 날**
        조용히 바뀌면 안 된다. 표에 직접 심어서 잰다.
        """
        row = await self.a_set()
        await self.an_origin(row, CautionSectionKey.EMERGENCY, body="[합성] 승인된 응급 문장")
        staff = await self.a_staff(["doctor"], "key258-d")
        await DoctorGuideCopy.create(
            hospital_id=staff.hospital_id,
            doctor_id=None,
            prescription_set_id=row.prescription_set_id,
            section_key=CautionSectionKey.EMERGENCY,
            body="원장님이 고친 응급 문장",
        )

        parts = await self.sections_of(staff, row)

        assert parts["emergency"]["preview"] == "[합성] 승인된 응급 문장", "안전 문장에 문구가 얹혔다"

    async def test_the_preview_is_letter_for_letter_what_generate_writes(self) -> None:
        """🚩 **인수조건 ②** — 미리보기와 생성이 같은 글자를 낸다.

        근사치가 아니다. 처방 행이 없는 진료는 실제로 도달하는 상태이고
        (`_medication_body` 의 `if not lines: return guidance`), 그 진료의
        `generate()` 결과와 **글자까지** 같아야 한다.

        이 검사가 이 티켓에서 가장 값지다 — 규칙이 두 벌로 갈리는 날 운다.
        """
        row = await self.a_set(SET_NAME)
        for section in (CautionSectionKey.CAUTION, CautionSectionKey.LIFE, CautionSectionKey.MEDICATION):
            await self.an_origin(row, section, body=f"[합성] 승인된 {section.value} 문구")
        await self.an_origin(row, CautionSectionKey.EMERGENCY, body="[합성] 승인된 응급 문장")
        staff = await self.a_staff(["doctor"], "key258-e")
        await self.save(staff, row, MINE, "caution")
        await self.save(staff, row, "원장님이 고친 생활지도", "life")

        preview = await self.sections_of(staff, row)
        visit = await self.a_visit_ready_for_generation(staff, row)
        guide = await GuideService().generate(_Actor(staff), visit.visit_id)

        written = {
            str(part.section_key): part.generated_body
            for part in await GuideSection.filter(guide_document_id=guide.guide_document_id)
        }
        for key in (
            GuideSectionKey.MEDICATION,
            GuideSectionKey.CAUTION,
            GuideSectionKey.EMERGENCY,
            GuideSectionKey.LIFE,
        ):
            assert preview[key.value]["preview"] == written[key.value], (
                f"{key.value} 가 갈렸다 — 미리보기 {preview[key.value]['preview']!r} vs 생성 {written[key.value]!r}"
            )

    async def test_the_drug_list_is_added_on_top_of_what_the_preview_shows(self) -> None:
        """**화면이 하는 약속을 그대로 잰다.**

        미리보기 아래에 「회색 줄은 진료마다 판독값으로 채워집니다 — 이 자리에
        그 환자의 약이 들어갑니다」라고 적었다. 그 말이 참이려면 실제 본문이
        **약 목록 + 미리보기 그대로**여야 한다.

        감싸는 자리가 사라지면(또는 미리보기가 감싼 것을 보이면) 그 ⓘ 줄이
        거짓이 된다 — 화면의 말과 코드가 갈리는 자리다.
        """
        row = await self.a_set(SET_NAME)
        await self.an_origin(row, CautionSectionKey.MEDICATION, body="[합성] 승인된 복약지도")
        await self.an_origin(row, CautionSectionKey.CAUTION)
        await self.an_origin(row, CautionSectionKey.EMERGENCY, body="[합성] 승인된 응급 문장")
        staff = await self.a_staff(["doctor"], "key258-f")

        preview = (await self.sections_of(staff, row))["medication"]["preview"]
        visit = await self.a_visit_ready_for_generation(staff, row)
        await PrescriptionItem.create(
            prescription=await Prescription.get(visit_id=visit.visit_id),
            name="비잔정(디에노게스트) 2mg",
            frequency="1일 1회",
            duration_days=84,
        )
        guide = await GuideService().generate(_Actor(staff), visit.visit_id)

        written = await GuideSection.get(
            guide_document_id=guide.guide_document_id, section_key=GuideSectionKey.MEDICATION
        )
        assert written.generated_body != preview, "처방 행이 있는데 안 감쌌다"
        assert written.generated_body.endswith(preview), (
            f"미리보기가 실제 본문의 끝이 아니다 — 화면의 「이 자리에 약이 들어갑니다」가 거짓이 된다\n"
            f"미리보기: {preview!r}\n실제: {written.generated_body!r}"
        )
        assert written.generated_body.startswith("처방된 복약 정보"), "약 목록 머리가 없다"
        assert "84일분" in written.generated_body, "처방일수가 안 실렸다"

    async def a_visit_ready_for_generation(self, staff: Staff, row: PrescriptionSet) -> Visit:
        """생성이 통과할 만큼만 세운다 — **처방 행은 안 만든다.**

        처방 행이 없는 것이 이 검사의 요점이다. 설정 화면이 보는 상태가 그것이고,
        실제로 도달하는 상태이기도 하다.
        """
        patient = await Patient.create(
            hospital_id=staff.hospital_id,
            hospital_patient_no="SYN-KEY258-01",
            name="합성환자",
            birth_date="1990-05-15",
            phone="01012345678",
        )
        visit = await Visit.create(
            hospital_id=staff.hospital_id,
            patient=patient,
            doctor_id=staff.staff_id,
            visited_at=datetime(2026, 9, 7, 0, 0, tzinfo=UTC),
        )
        await Prescription.create(visit=visit, prescription_set=row.name)
        job = await OcrJob.create(
            ocr_job_id="ocr_key258_01",
            hospital_id=staff.hospital_id,
            visit_id=visit.visit_id,
            requested_by=staff.staff_id,
            status=OcrJobStatus.COMPLETED,
        )
        result = await OcrResult.create(ocr_job=job, model_name="synthetic-key258")
        await OcrField.create(
            ocr_result=result,
            field_type="PRESCRIPTION_SET",
            extracted_value=row.name,
            is_confirmed=True,
        )
        return visit


class _Actor:
    """`GuideService.generate` 가 보는 만큼만."""

    def __init__(self, staff: Staff) -> None:
        self.user_id = staff.staff_id
        self.staff_id = staff.staff_id
        self.hospital_id = staff.hospital_id
        self.roles = frozenset({"doctor"})
