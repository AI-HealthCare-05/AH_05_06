"""의사가 고친 안내문 문구가 실제로 환자에게 나간다 — KEY-243.

`#183`(KEY-234)이 D2-2 「안내문 고치기」 화면과 `DoctorGuideCopy` 를 만들었는데,
**안내문을 만드는 `GuideService.generate()` 가 그것을 읽지 않았다.** 의사가
문구를 고쳐도 환자에게는 원본이 나갔다.

고칠 수 있게 해 놓고 반영하지 않는 것이 제일 나쁘다 — 의사는 고쳤다고 믿는다.
화면에는 고친 글이 그대로 남아 있어서, 나간 뒤에도 틀린 줄 모른다.

**담당 의사 기준이다.** 만드는 사람(스탭일 수 있다)이 아니라 `visit.doctor_id` —
그 글은 담당 의사 이름으로 환자에게 간다.
"""

from datetime import UTC, datetime

from app.models.catalog import CautionSectionKey, DoctorGuideCopy, PrescriptionSet
from app.models.patients import Patient
from app.models.prescriptions import Prescription
from app.models.staffs import Hospital, Staff
from app.models.visits import GuideSectionKey, Visit
from app.tests.guide_apis.test_key165_drug_caution import (
    DrugCautionTestCase,
    attach_confirmed_ocr,
    make_approved_content,
    make_clinic,
    make_staff,
)

SET_NAME = "자궁내막증 · 비잔 (계속)"
APPROVED = "승인된 원본 주의사항 — 복용 중 부정출혈이 있을 수 있습니다."
EDITED = "박연 원장이 고친 문구 — 부정출혈이 2주 넘게 이어지면 연락 주세요."


async def make_visit_with_doctor(
    hospital: Hospital,
    doctor: Staff | None,
    set_name: str | None = SET_NAME,
    chart: str = "KEY243-01",
) -> Visit:
    """**담당 의사를 고른 진료.** `make_visit` 은 담당을 안 붙여서 여기서 짓는다."""
    patient = await Patient.create(
        hospital_id=hospital.hospital_id,
        hospital_patient_no=chart,
        name="합성환자",
        birth_date="1990-05-15",
        phone="01012345678",
        sms_consent=True,
    )
    visit = await Visit.create(
        hospital_id=hospital.hospital_id,
        patient=patient,
        doctor_id=doctor.staff_id if doctor else None,
        visited_at=datetime(2026, 9, 2, 9, 0, tzinfo=UTC),
    )
    if set_name:
        await Prescription.create(visit=visit, prescription_set=set_name)
    return visit


async def save_doctor_copy(
    hospital: Hospital,
    doctor: Staff,
    set_name: str,
    body: str,
    section_key: CautionSectionKey = CautionSectionKey.CAUTION,
) -> DoctorGuideCopy:
    """D2-2 가 저장하는 것과 같은 행을 만든다."""
    prescription_set, _ = await PrescriptionSet.get_or_create(name=set_name)
    return await DoctorGuideCopy.create(
        hospital_id=hospital.hospital_id,
        doctor_id=doctor.staff_id,
        prescription_set_id=prescription_set.prescription_set_id,
        section_key=section_key,
        body=body,
        updated_by=doctor.staff_id,
    )


class TestDoctorCopyWins(DrugCautionTestCase):
    async def test_the_edited_wording_reaches_the_patient(self) -> None:
        """**인수조건 1** — 고친 문구가 원본을 이긴다."""
        clinic = await make_clinic()
        doctor = await make_staff(clinic, "k243-doc", ["doctor"])
        staff = await make_staff(clinic, "k243-staff", ["staff"])
        await make_approved_content(SET_NAME, CautionSectionKey.CAUTION, APPROVED)
        await save_doctor_copy(clinic, doctor, SET_NAME, EDITED)
        visit = await make_visit_with_doctor(clinic, doctor)
        await attach_confirmed_ocr(visit, staff.staff_id)

        response = await self.generate(visit, staff)

        assert response.status_code == 201, response.text
        sections = await self.sections_from_db(visit.visit_id)
        assert sections[GuideSectionKey.CAUTION].generated_body == EDITED

    async def test_staff_generating_still_uses_the_doctors_wording(self) -> None:
        """**만드는 사람이 아니라 담당 의사 기준이다.**

        스탭이 만들어도 그 글은 담당 의사 이름으로 환자에게 간다. 만드는
        사람으로 찾으면 스탭이 만든 안내문에는 아무 문구도 안 붙는다 —
        스탭에게는 고쳐 둔 문구가 있을 리 없어서다.
        """
        clinic = await make_clinic()
        doctor = await make_staff(clinic, "k243-doc2", ["doctor"])
        staff = await make_staff(clinic, "k243-staff2", ["staff"])
        await make_approved_content(SET_NAME, CautionSectionKey.CAUTION, APPROVED)
        await save_doctor_copy(clinic, doctor, SET_NAME, EDITED)
        visit = await make_visit_with_doctor(clinic, doctor, chart="KEY243-02")
        await attach_confirmed_ocr(visit, staff.staff_id)

        await self.generate(visit, staff)

        sections = await self.sections_from_db(visit.visit_id)
        assert sections[GuideSectionKey.CAUTION].generated_body == EDITED

    async def test_the_origin_link_is_kept(self) -> None:
        """**어느 승인 문구에서 나왔는지는 남는다.**

        의사가 고쳤어도 `drug_caution_content_id` 는 원본을 가리킨 채로 둔다.
        나중에 원본이 개정되면 무엇을 다시 봐야 하는지 알 수 있어야 한다.
        """
        clinic = await make_clinic()
        doctor = await make_staff(clinic, "k243-doc3", ["doctor"])
        staff = await make_staff(clinic, "k243-staff3", ["staff"])
        origin = await make_approved_content(SET_NAME, CautionSectionKey.CAUTION, APPROVED)
        await save_doctor_copy(clinic, doctor, SET_NAME, EDITED)
        visit = await make_visit_with_doctor(clinic, doctor, chart="KEY243-03")
        await attach_confirmed_ocr(visit, staff.staff_id)

        await self.generate(visit, staff)

        sections = await self.sections_from_db(visit.visit_id)
        caution = sections[GuideSectionKey.CAUTION]
        assert caution.generated_body == EDITED
        assert caution.drug_caution_content_id == origin.drug_caution_content_id


class TestFallsBackWhenNoCopy(DrugCautionTestCase):
    """**인수조건 2** — 고쳐 둔 것이 없으면 원본으로 내려간다."""

    async def test_no_copy_uses_the_approved_original(self) -> None:
        clinic = await make_clinic()
        doctor = await make_staff(clinic, "k243-doc4", ["doctor"])
        staff = await make_staff(clinic, "k243-staff4", ["staff"])
        await make_approved_content(SET_NAME, CautionSectionKey.CAUTION, APPROVED)
        visit = await make_visit_with_doctor(clinic, doctor, chart="KEY243-04")
        await attach_confirmed_ocr(visit, staff.staff_id)

        await self.generate(visit, staff)

        sections = await self.sections_from_db(visit.visit_id)
        assert sections[GuideSectionKey.CAUTION].generated_body == APPROVED

    async def test_another_doctors_wording_is_not_borrowed(self) -> None:
        """**남이 고친 문구를 빌려 쓰지 않는다.**

        의사마다 자기 문구다. 담당이 아닌 의사 것이 붙으면 그 사람 이름으로
        남의 글이 나간다.
        """
        clinic = await make_clinic()
        mine = await make_staff(clinic, "k243-doc5", ["doctor"])
        other = await make_staff(clinic, "k243-doc6", ["doctor"])
        staff = await make_staff(clinic, "k243-staff5", ["staff"])
        await make_approved_content(SET_NAME, CautionSectionKey.CAUTION, APPROVED)
        await save_doctor_copy(clinic, other, SET_NAME, EDITED)
        visit = await make_visit_with_doctor(clinic, mine, chart="KEY243-05")
        await attach_confirmed_ocr(visit, staff.staff_id)

        await self.generate(visit, staff)

        sections = await self.sections_from_db(visit.visit_id)
        assert sections[GuideSectionKey.CAUTION].generated_body == APPROVED

    async def test_another_clinic_wording_is_not_borrowed(self) -> None:
        """의원 범위도 재야 한다.

        **같은 의사 번호를 다른 의원에 둔다.** 다른 번호로 두면 `doctor_id`
        하나만으로도 안 걸려서, 의원 범위를 빼도 검사가 통과한다 — 실제로
        처음에 그렇게 써 놓고 뮤테이션에서 안 물어 드러났다.

        `DoctorGuideCopy.doctor_id` 는 외래키가 아니라 숫자라 다른 의원 행에
        같은 번호를 넣을 수 있다.
        """
        mine = await make_clinic("우리의원")
        theirs = await make_clinic("다른의원")
        doctor = await make_staff(mine, "k243-doc7", ["doctor"])
        staff = await make_staff(mine, "k243-staff6", ["staff"])
        await make_approved_content(SET_NAME, CautionSectionKey.CAUTION, APPROVED)
        prescription_set, _ = await PrescriptionSet.get_or_create(name=SET_NAME)
        await DoctorGuideCopy.create(
            hospital_id=theirs.hospital_id,
            doctor_id=doctor.staff_id,  # ← 같은 번호, 다른 의원
            prescription_set_id=prescription_set.prescription_set_id,
            section_key=CautionSectionKey.CAUTION,
            body=EDITED,
        )
        visit = await make_visit_with_doctor(mine, doctor, chart="KEY243-06")
        await attach_confirmed_ocr(visit, staff.staff_id)

        await self.generate(visit, staff)

        sections = await self.sections_from_db(visit.visit_id)
        assert sections[GuideSectionKey.CAUTION].generated_body == APPROVED

    async def test_a_visit_without_a_doctor_uses_the_original(self) -> None:
        """담당이 없으면 **고른 의사가 없다는 뜻**이라 원본을 쓴다."""
        clinic = await make_clinic()
        staff = await make_staff(clinic, "k243-staff7", ["staff"])
        await make_approved_content(SET_NAME, CautionSectionKey.CAUTION, APPROVED)
        visit = await make_visit_with_doctor(clinic, None, chart="KEY243-07")
        await attach_confirmed_ocr(visit, staff.staff_id)

        await self.generate(visit, staff)

        sections = await self.sections_from_db(visit.visit_id)
        assert sections[GuideSectionKey.CAUTION].generated_body == APPROVED

    async def test_a_different_prescription_set_is_not_borrowed(self) -> None:
        """처방이 다르면 문구도 다르다 — 세트마다 고쳐 두는 것이 D2-2 다."""
        clinic = await make_clinic()
        doctor = await make_staff(clinic, "k243-doc9", ["doctor"])
        staff = await make_staff(clinic, "k243-staff8", ["staff"])
        await make_approved_content(SET_NAME, CautionSectionKey.CAUTION, APPROVED)
        await save_doctor_copy(clinic, doctor, "PCOS · 메트포르민 (계속)", EDITED)
        visit = await make_visit_with_doctor(clinic, doctor, chart="KEY243-08")
        await attach_confirmed_ocr(visit, staff.staff_id)

        await self.generate(visit, staff)

        sections = await self.sections_from_db(visit.visit_id)
        assert sections[GuideSectionKey.CAUTION].generated_body == APPROVED


class TestEmergencyStaysLocked(DrugCautionTestCase):
    """**인수조건 3 — 의료 안전.** 응급 문장은 이 길로 안 바뀐다.

    `emergency` 는 `locked=True` 이고 사람이 못 고치는 글이다(KEY-150).
    `guide_copy.py` 의 `EDITABLE_SECTIONS` 도 `caution` 하나뿐이라 D2-2 는
    응급 문구를 저장하지 않는다.

    그래도 **표에 행이 생기는 날**을 대비해 못 박는다 — 다른 경로로 한 줄이
    들어오는 순간 응급 문장이 조용히 바뀌면 안 된다.
    """

    async def test_an_emergency_copy_row_is_ignored(self) -> None:
        clinic = await make_clinic()
        doctor = await make_staff(clinic, "k243-doc10", ["doctor"])
        staff = await make_staff(clinic, "k243-staff9", ["staff"])
        approved_emergency = "🚨 승인된 응급 문장 — 심한 복통이면 응급실로 가세요."
        # 주의사항 원본도 세운다 — 응급 문구가 그 칸으로 새는지 보려면
        # 비교할 값이 있어야 한다(없으면 범용 폴백이라 비교가 흐려진다).
        await make_approved_content(SET_NAME, CautionSectionKey.CAUTION, APPROVED)
        await make_approved_content(SET_NAME, CautionSectionKey.EMERGENCY, approved_emergency)
        await save_doctor_copy(clinic, doctor, SET_NAME, "누군가 고친 응급 문장", CautionSectionKey.EMERGENCY)
        visit = await make_visit_with_doctor(clinic, doctor, chart="KEY243-09")
        await attach_confirmed_ocr(visit, staff.staff_id)

        await self.generate(visit, staff)

        sections = await self.sections_from_db(visit.visit_id)
        emergency = sections[GuideSectionKey.EMERGENCY]
        assert emergency.generated_body == approved_emergency, "응급 문장이 바뀌었다"
        assert emergency.locked is True

        # **주의사항 칸으로도 새면 안 된다.** 조회에서 갈래를 빼면 이 행이
        # 첫 줄로 잡혀 응급 문장이 주의사항 자리에 들어간다 — 응급 문장은
        # 그대로인데 엉뚱한 칸에 한 벌 더 생기는 셈이다.
        assert sections[GuideSectionKey.CAUTION].generated_body == APPROVED, "응급 문구가 주의사항 칸으로 샜다"
