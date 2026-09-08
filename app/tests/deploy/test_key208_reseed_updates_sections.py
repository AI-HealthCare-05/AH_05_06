"""재시드하면 안내문 본문이 카탈로그를 따라간다 — KEY-208.

`seed_smoke_fixture` 는 **다시 돌리는 것을 전제**로 짜여 있다. `GuideDocument`
와 `PatientGuideLink` 는 이미 갱신 분기를 갖고 있는데 `GuideSection` 만
`get_or_create` 뿐이었다. 그래서 승인 문구를 고친 뒤 같은 명령을 다시 돌려도
**이미 시드된 Pilot DB 의 본문은 옛 글 그대로**였다 (이희진 님 `#158` 리뷰 ④).

옆 검사(`test_key200_smoke_fixture.py`)는 DB 없이 소스만 읽어 계약을 잰다.
**여기서는 그 길을 쓰지 않는다** — 「`update` 라는 낱말이 있는가」를 재면 엉뚱한
칸을 갱신해도 초록이다. 카탈로그를 실제로 고치고 두 번 돌려 **본문이 따라오는지**
본다.
"""

import os
from datetime import UTC, datetime

from tortoise.contrib.test import TestCase

from app.models.catalog import ApprovalStatus, CautionSectionKey, DrugCautionContent, PrescriptionSet
from app.models.patients import Patient
from app.models.prescriptions import Prescription
from app.models.staffs import Hospital, Staff
from app.models.visits import GuideDocument, GuideSection, GuideSectionKey, Visit
from scripts.seed import SMOKE_CHART_NO, SMOKE_LINK_TOKEN_ENV, seed_smoke_fixture

SET_NAME = "PCOS · 야즈 (처음)"

#: smoke 가 멈추지 않으려면 이 둘은 승인본이 있어야 한다 — 나머지 둘은 폴백이 선다.
FIRST_WORDS = (
    (CautionSectionKey.CAUTION, "첫 주의 문구"),
    (CautionSectionKey.EMERGENCY, "첫 응급 문구"),
    (CautionSectionKey.MEDICATION, "첫 복약 문구"),
    (CautionSectionKey.LIFE, "첫 생활 문구"),
)


class ReseedUpdatesSectionsTestCase(TestCase):
    async def approve(self, section: CautionSectionKey, body: str, *, version: str) -> DrugCautionContent:
        """그 갈래의 승인 문구를 한 벌 세운다 — 옛 승인은 폐기로 내린다.

        `approved_key` 가 유니크라 옛 행을 비우지 않으면 새 승인이 서지 않는다
        (KEY-180 §3). 실제 승인(`approve_version`)이 하는 것과 같은 순서다.
        """
        prescription_set = await PrescriptionSet.get(name=SET_NAME)
        await DrugCautionContent.filter(
            prescription_set=prescription_set,
            section_key=section,
            approval_status=ApprovalStatus.APPROVED,
        ).update(approval_status=ApprovalStatus.DEPRECATED, approved_key=None)
        return await DrugCautionContent.create(
            prescription_set=prescription_set,
            section_key=section,
            body=body,
            source_name="의약품안전나라 제품 허가사항",
            source_org="식품의약품안전처",
            source_url="https://nedrug.mfds.go.kr/TEST-ONLY/key208",
            verified_at="2026-09-01",
            content_version=version,
            source_grade="A",
            approval_status=ApprovalStatus.APPROVED,
            approved_key=f"{prescription_set.prescription_set_id}:{section.value}",
        )

    async def make_world(self) -> dict[str, Hospital]:
        """smoke fixture 가 붙을 자리를 세운다 — 차트번호까지 시드가 찾는 그것으로."""
        clinic = await Hospital.create(name="여성의원 KEY208")
        doctor = await Staff.create(
            hospital=clinic,
            login_id="key208_doctor",
            password_hash="ignored-here",
            name="합성원장",
            roles=["doctor"],
            must_change_password=False,
        )
        patient = await Patient.create(
            hospital_id=clinic.hospital_id,
            hospital_patient_no=SMOKE_CHART_NO,
            name="합성환자",
            birth_date="1990-05-15",
            phone="01012345678",
        )
        visit = await Visit.create(
            hospital_id=clinic.hospital_id,
            patient=patient,
            doctor_id=doctor.staff_id,
            visited_at=datetime(2026, 9, 3, 3, 0, tzinfo=UTC),
        )
        await PrescriptionSet.get_or_create(name=SET_NAME)
        await Prescription.create(visit=visit, prescription_set=SET_NAME)
        for section, body in FIRST_WORDS:
            await self.approve(section, body, version="2026-09-01")
        return {"H1": clinic}

    async def sow(self, hospitals: dict[str, Hospital]) -> None:
        """시드 명령이 하는 그대로 부른다 — 토큰은 사람이 넣어 주는 값이다."""
        os.environ[SMOKE_LINK_TOKEN_ENV] = "key208-synthetic-token"
        try:
            await seed_smoke_fixture(hospitals)
        finally:
            os.environ.pop(SMOKE_LINK_TOKEN_ENV, None)

    async def body_of(self, key: GuideSectionKey) -> str | None:
        row = await GuideSection.filter(section_key=key).first()
        return row.generated_body if row else None

    async def test_reseeding_carries_the_new_catalog_wording(self) -> None:
        """**인수조건 ①** — 문구를 고치고 같은 명령을 다시 돌리면 본문이 따라온다."""
        hospitals = await self.make_world()
        await self.sow(hospitals)
        assert await self.body_of(GuideSectionKey.CAUTION) == "첫 주의 문구", "첫 시드가 승인 문구를 안 썼다"

        await self.approve(CautionSectionKey.CAUTION, "고친 주의 문구", version="2026-09-07")
        await self.sow(hospitals)

        got = await self.body_of(GuideSectionKey.CAUTION)
        assert got == "고친 주의 문구", f"재시드했는데 옛 글이 남았다 — {got!r}"

    async def test_reseeding_updates_every_catalogued_section(self) -> None:
        """네 갈래 모두 따라온다 — caution 만 고치면 나머지 셋이 조용히 뒤쳐진다.

        KEY-265 가 복약·생활까지 카탈로그로 옮겼다. 갱신을 주의·응급에만 달면
        같은 결함이 두 갈래에 그대로 남는다.
        """
        hospitals = await self.make_world()
        await self.sow(hospitals)

        pairs = (
            (CautionSectionKey.MEDICATION, GuideSectionKey.MEDICATION),
            (CautionSectionKey.CAUTION, GuideSectionKey.CAUTION),
            (CautionSectionKey.EMERGENCY, GuideSectionKey.EMERGENCY),
            (CautionSectionKey.LIFE, GuideSectionKey.LIFE),
        )
        for catalog_key, _ in pairs:
            await self.approve(catalog_key, f"고친 {catalog_key.value} 문구", version="2026-09-07")
        await self.sow(hospitals)

        for catalog_key, section_key in pairs:
            got = await self.body_of(section_key)
            assert got == f"고친 {catalog_key.value} 문구", f"{section_key.value} 가 안 따라왔다 — {got!r}"

    async def test_reseeding_does_not_stack_rows(self) -> None:
        """**인수조건 ②** — 갱신이지 덧붙이기가 아니다."""
        hospitals = await self.make_world()
        await self.sow(hospitals)
        first = await GuideSection.all().count()

        await self.approve(CautionSectionKey.LIFE, "고친 생활 문구", version="2026-09-07")
        await self.sow(hospitals)

        assert await GuideSection.all().count() == first, "재시드가 절 행을 늘렸다"
        assert await GuideDocument.all().count() == 1, "안내문이 둘이 됐다"

    async def test_a_doctors_edit_survives_reseeding(self) -> None:
        """**원장님이 고친 글은 안 덮는다.**

        모델이 `generated_body`(생성 원문)와 `edited_body`(사람이 고친 것)를 일부러
        따로 둔다 — 「AI 가 이렇게 썼는데 원장님이 이렇게 고쳤다」를 다음 초안에
        쓰려는 것이다(D1-2). 재시드가 그것을 덮으면 손으로 고친 글이 소리 없이
        사라지고, 사라졌다는 사실조차 남지 않는다.
        """
        hospitals = await self.make_world()
        await self.sow(hospitals)
        await GuideSection.filter(section_key=GuideSectionKey.CAUTION).update(edited_body="원장님이 고친 글")

        await self.approve(CautionSectionKey.CAUTION, "고친 주의 문구", version="2026-09-07")
        await self.sow(hospitals)

        row = await GuideSection.filter(section_key=GuideSectionKey.CAUTION).first()
        assert row is not None
        assert row.edited_body == "원장님이 고친 글", f"사람이 고친 글을 덮었다 — {row.edited_body!r}"
        assert row.generated_body == "고친 주의 문구", "원문은 따라와야 한다"

    async def test_the_evidence_id_follows_the_wording(self) -> None:
        """근거 버전도 함께 따라간다.

        `drug_caution_content_id` 는 「이 글이 어느 승인본에서 왔나」다. 본문만
        바뀌고 이 칸이 옛 행을 가리키면, 감사에서 대는 근거가 화면의 글과 다른
        글이 된다.
        """
        hospitals = await self.make_world()
        await self.sow(hospitals)
        before = await GuideSection.filter(section_key=GuideSectionKey.CAUTION).first()
        assert before is not None
        assert before.drug_caution_content_id is not None, "첫 시드가 근거를 안 남겼다"

        fresh = await self.approve(CautionSectionKey.CAUTION, "고친 주의 문구", version="2026-09-07")
        await self.sow(hospitals)

        after = await GuideSection.filter(section_key=GuideSectionKey.CAUTION).first()
        assert after is not None
        assert after.drug_caution_content_id == fresh.drug_caution_content_id, (
            f"본문은 바뀌었는데 근거가 옛 버전을 가리킨다 — {after.drug_caution_content_id}"
        )

    async def test_the_emergency_section_stays_locked(self) -> None:
        """🚨 응급 절의 잠금은 재시드를 지나도 남는다 (KEY-150·KEY-165).

        `locked` 도 함께 쓰는 자리라, 갱신 분기가 이 값을 흘리면 사람이 못 고쳐야
        할 문장이 **고칠 수 있는 상태로** 열린다.
        """
        hospitals = await self.make_world()
        await self.sow(hospitals)
        await self.approve(CautionSectionKey.EMERGENCY, "고친 응급 문구", version="2026-09-07")
        await self.sow(hospitals)

        row = await GuideSection.filter(section_key=GuideSectionKey.EMERGENCY).first()
        assert row is not None
        assert row.locked is True, "응급 절의 잠금이 재시드에 풀렸다"
        assert row.generated_body == "고친 응급 문구"

    async def test_a_missing_approved_wording_still_stops(self) -> None:
        """**인수조건 ③** — 승인 문구가 없는 세트면 폴백을 만들지 않고 멈춘다.

        갱신 분기를 더하면서 이 게이트를 지나치게 되면, 재시드가 **범용 폴백
        문구를 실은 「승인된」 안내문**을 만든다 — KEY-200 이 막으려던 그것이다.
        """
        hospitals = await self.make_world()
        prescription_set = await PrescriptionSet.get(name=SET_NAME)
        await DrugCautionContent.filter(
            prescription_set=prescription_set,
            section_key=CautionSectionKey.CAUTION,
        ).update(approval_status=ApprovalStatus.DEPRECATED, approved_key=None)

        await self.sow(hospitals)

        assert await GuideDocument.all().count() == 0, "승인 주의 문구가 없는데 안내문을 만들었다"
