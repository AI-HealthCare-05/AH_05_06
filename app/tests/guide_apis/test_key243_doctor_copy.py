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
from app.services import guide_defaults
from app.services.guides import GuideService
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
    doctor: Staff | None,
    set_name: str,
    body: str,
    section_key: CautionSectionKey = CautionSectionKey.CAUTION,
) -> DoctorGuideCopy:
    """D2-2 가 저장하는 것과 같은 행을 만든다."""
    prescription_set, _ = await PrescriptionSet.get_or_create(name=set_name)
    return await DoctorGuideCopy.create(
        hospital_id=hospital.hospital_id,
        doctor_id=doctor.staff_id if doctor else None,
        prescription_set_id=prescription_set.prescription_set_id,
        section_key=section_key,
        body=body,
        updated_by=doctor.staff_id if doctor else None,
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

    async def test_a_doctor_generating_does_not_lend_their_own_wording(self) -> None:
        """🚨 **담당이 아닌 의사가 만들어도 제 문구를 빌려주지 않는다.**

        `generate()` 는 담당이 아니어도 같은 의원의 아무 의사·스탭이나 부를 수
        있다 — 역할만 보고, 진료 조회도 `hospital_id` 로만 범위를 잡는다.
        그래서 「담당 것이 없으면 만든 사람 것」으로 내려가면 이렇게 된다:

            의사 B 가 세트 S 문구를 고쳐 둔다
            담당 의사 A 는 S 를 고친 적이 없다
            B 가 (담당이 아닌데) A 의 진료로 generate 를 부른다
            → **B 가 쓴 글이 A 이름으로 환자에게 나간다**

        **바로 위 검사(`test_another_doctors_wording_is_not_borrowed`)로는 못
        잡는다.** 그쪽은 생성자가 **스탭**이라 빌려 올 문구가 애초에 없어서,
        폴백이 헛돌고도 통과한다. 생성자가 **제 문구를 가진 의사 본인**인
        경우가 진짜 위험 경로다.
        """
        clinic = await make_clinic()
        mine = await make_staff(clinic, "k243-own1", ["doctor"])
        other = await make_staff(clinic, "k243-own2", ["doctor"])
        await make_approved_content(SET_NAME, CautionSectionKey.CAUTION, APPROVED)
        await save_doctor_copy(clinic, other, SET_NAME, EDITED)
        visit = await make_visit_with_doctor(clinic, mine, chart="KEY243-OWN")
        await attach_confirmed_ocr(visit, other.staff_id)

        # **담당이 아닌 `other` 가 직접 만든다.** 여기가 갈리는 자리다.
        response = await self.generate(visit, other)

        assert response.status_code == 201, response.text
        sections = await self.sections_from_db(visit.visit_id)
        assert sections[GuideSectionKey.CAUTION].generated_body == APPROVED, (
            "만든 사람 문구가 담당 의사 이름으로 나갔다"
        )

    async def test_an_edited_caution_never_leaks_into_emergency(self) -> None:
        """🚨 **의사가 고친 주의사항이 응급 칸으로 새지 않는다.**

        위 두 검사로는 못 잡는다. `test_an_emergency_copy_row_is_ignored` 는
        **응급** 문구만 저장하는데, `_doctor_copies` 가 그 갈래를 아예 안 읽어
        사전이 비어 있다 — 응급 자리에 사전을 물려도 티가 안 난다.
        `test_the_locked_section_never_enters_the_lookup` 은 **조회**를 재고,
        이것은 **환자에게 나가는 값**을 잰다.

        재려면 **고칠 수 있는 갈래에 문구가 있는 상태**여야 한다. 그래야
        「응급에도 그 사전을 쓴다」는 실수가 값으로 드러난다. 응급은 승인
        안 거친 문장이 나가면 안 되는 자리다(KEY-150).
        """
        clinic = await make_clinic()
        doctor = await make_staff(clinic, "k243-leak", ["doctor"])
        staff = await make_staff(clinic, "k243-leak-s", ["staff"])
        approved_emergency = "🚨 승인된 응급 문장 — 심한 복통이면 응급실로 가세요."
        await make_approved_content(SET_NAME, CautionSectionKey.CAUTION, APPROVED)
        await make_approved_content(SET_NAME, CautionSectionKey.EMERGENCY, approved_emergency)
        await save_doctor_copy(clinic, doctor, SET_NAME, EDITED, CautionSectionKey.CAUTION)
        visit = await make_visit_with_doctor(clinic, doctor, chart="KEY243-LEAK")
        await attach_confirmed_ocr(visit, staff.staff_id)

        await self.generate(visit, staff)

        sections = await self.sections_from_db(visit.visit_id)
        assert sections[GuideSectionKey.CAUTION].generated_body == EDITED, "의사 문구가 안 나갔다"
        assert sections[GuideSectionKey.EMERGENCY].generated_body == approved_emergency, (
            "의사가 고친 주의사항이 응급 칸으로 샜다"
        )


class TestEveryEditableSectionReachesThePatient(DrugCautionTestCase):
    """**고칠 수 있는 갈래는 다 나가야 한다.**

    설정이 고칠 수 있는 갈래를 셋으로 넓혔는데(복약지도·주의사항·생활지도)
    생성은 `caution` 하나만 읽고 있었다. 복약지도를 고치면 **저장은 200 이고
    환자에게는 안 갔다** — 고칠 수 있게 해 놓고 반영하지 않는 것이 제일
    나쁘다. 의사는 고쳤다고 믿는다.
    """

    async def test_medication_wording_reaches_the_patient(self) -> None:
        """복약지도를 고치면 그 글이 나간다 — **진료별 줄은 남는다.**"""
        clinic = await make_clinic()
        doctor = await make_staff(clinic, "k243-med", ["doctor"])
        staff = await make_staff(clinic, "k243-med-s", ["staff"])
        await save_doctor_copy(clinic, doctor, SET_NAME, "고친 복약 문장", CautionSectionKey.MEDICATION)
        visit = await make_visit_with_doctor(clinic, doctor, chart="KEY243-M1")
        await attach_confirmed_ocr(visit, staff.staff_id)

        response = await self.generate(visit, staff)

        assert response.status_code == 201, response.text
        body = (await self.sections_from_db(visit.visit_id))[GuideSectionKey.MEDICATION].generated_body
        assert body.endswith("고친 복약 문장"), f"고친 문구가 안 나갔다: {body!r}"
        assert "확정된 항목:" in body, "진료별 줄이 사라졌다 — 판독으로 확정된 사실이다"

    async def test_life_wording_reaches_the_patient(self) -> None:
        """생활지도를 고치면 그 글이 통째로 나간다."""
        clinic = await make_clinic()
        doctor = await make_staff(clinic, "k243-life", ["doctor"])
        staff = await make_staff(clinic, "k243-life-s", ["staff"])
        await save_doctor_copy(clinic, doctor, SET_NAME, "고친 생활 문장", CautionSectionKey.LIFE)
        visit = await make_visit_with_doctor(clinic, doctor, chart="KEY243-L1")
        await attach_confirmed_ocr(visit, staff.staff_id)

        response = await self.generate(visit, staff)

        assert response.status_code == 201, response.text
        sections = await self.sections_from_db(visit.visit_id)
        assert sections[GuideSectionKey.LIFE].generated_body == "고친 생활 문장"

    async def test_sections_fall_back_one_by_one(self) -> None:
        """**갈래마다 따로 내려간다.**

        담당이 주의사항만 고치고 의원 공통이 복약지도만 가졌으면 둘 다 나가야
        한다. 통째로 한 벌만 고르면 한쪽이 통째로 묻힌다.

        **「만든 사람」 층으로는 재지 않는다.** 그 층은 오귀속이라 걷었다 —
        담당이 아닌 사람이 만들면 그 사람 글이 담당 이름으로 나갔다.
        """
        clinic = await make_clinic()
        doctor = await make_staff(clinic, "k243-mix", ["doctor"])
        staff = await make_staff(clinic, "k243-mix-s", ["staff"])
        await save_doctor_copy(clinic, doctor, SET_NAME, "담당의 주의", CautionSectionKey.CAUTION)
        await save_doctor_copy(clinic, None, SET_NAME, "의원 공통 복약", CautionSectionKey.MEDICATION)
        visit = await make_visit_with_doctor(clinic, doctor, chart="KEY243-X1")
        await attach_confirmed_ocr(visit, staff.staff_id)

        response = await self.generate(visit, staff)

        assert response.status_code == 201, response.text
        sections = await self.sections_from_db(visit.visit_id)
        assert sections[GuideSectionKey.CAUTION].generated_body == "담당의 주의"
        assert sections[GuideSectionKey.MEDICATION].generated_body.endswith("의원 공통 복약")

    async def test_the_screen_shows_what_actually_goes_out(self) -> None:
        """**설정 화면의 「원본」이 실제로 나가는 글이어야 한다.**

        한동안 `guides.py` 가 기본 문구를 따로 들고 있었다. 셋은 우연히 같았고
        복약지도만 어긋나서, 설정 화면이 「원본」이라며 **실제로는 나가지 않는
        글**을 보였다. 고치는 사람이 그것을 기준으로 판단한다.
        """
        clinic = await make_clinic()
        doctor = await make_staff(clinic, "k243-org", ["doctor"])
        staff = await make_staff(clinic, "k243-org-s", ["staff"])
        visit = await make_visit_with_doctor(clinic, doctor, chart="KEY243-O1")
        await attach_confirmed_ocr(visit, staff.staff_id)

        response = await self.generate(visit, staff)

        assert response.status_code == 201, response.text
        sections = await self.sections_from_db(visit.visit_id)
        assert sections[GuideSectionKey.MEDICATION].generated_body.endswith(guide_defaults.MEDICATION)
        assert sections[GuideSectionKey.LIFE].generated_body == guide_defaults.LIFE
        assert sections[GuideSectionKey.CAUTION].generated_body == guide_defaults.CAUTION

    async def test_the_locked_section_never_enters_the_lookup(self) -> None:
        """**응급은 사전에 들어오지도 않는다.**

        지금은 응급 자리가 `copies` 를 안 보므로 사전에 섞여도 겉으로는 아무
        일이 없다. 그래서 결과만 보는 검사로는 못 잡는다 — 조회 자체를 잰다.
        누군가 나중에 응급 자리에 `copies` 를 물리는 날, **승인도 안 거친
        문장이 응급 안내로 나간다**(KEY-150). 그 날 걸려야 한다.
        """
        clinic = await make_clinic()
        doctor = await make_staff(clinic, "k243-lock", ["doctor"])
        await save_doctor_copy(clinic, doctor, SET_NAME, "누군가 고친 응급 문장", CautionSectionKey.EMERGENCY)
        await save_doctor_copy(clinic, doctor, SET_NAME, EDITED, CautionSectionKey.CAUTION)

        # 세트는 부르는 쪽이 찾아 넘긴다 — `generate()` 와 같은 길이다.
        prescription_set = await PrescriptionSet.filter(name=SET_NAME).first()
        found = await GuideService._doctor_copies(clinic.hospital_id, doctor.staff_id, prescription_set)

        assert CautionSectionKey.EMERGENCY not in found, "잠긴 갈래가 사전에 들어왔다"
        assert found[CautionSectionKey.CAUTION] == EDITED, "고칠 수 있는 갈래는 들어와야 한다"

    async def test_the_clinic_wording_reaches_every_doctors_patients(self) -> None:
        """**의원 공통 문구가 모든 의사의 환자에게 나간다** (2026-09-02 회의).

        전에는 문구가 고친 사람 개인 것이라, 원장 A 가 고치면 A 담당 환자에게만
        나갔다. 원장 B 는 같은 처방을 열어도 문구만 기본값으로 보여
        「아직 아무도 안 고쳤구나」로 읽었다. 처방 세트는 의원 공통인데 그 위에
        덧씌우는 표현만 개인 것이면 한 처방이 두 가지로 말해진다.
        """
        clinic = await make_clinic()
        wrote = await make_staff(clinic, "k255-a", ["doctor"])
        other = await make_staff(clinic, "k255-b", ["doctor"])
        staff = await make_staff(clinic, "k255-s", ["staff"])
        await save_doctor_copy(clinic, None, SET_NAME, "의원이 정한 주의")
        visit = await make_visit_with_doctor(clinic, other, chart="KEY255-C1")
        await attach_confirmed_ocr(visit, staff.staff_id)

        response = await self.generate(visit, staff)

        assert response.status_code == 201, response.text
        sections = await self.sections_from_db(visit.visit_id)
        assert sections[GuideSectionKey.CAUTION].generated_body == "의원이 정한 주의", (
            f"{wrote.staff_id} 가 고친 의원 공통 문구가 다른 의사 환자에게 안 나갔다"
        )

    async def test_a_personal_wording_still_wins_over_the_clinic_one(self) -> None:
        """**좁은 것이 넓은 것을 덮는다.**

        원장별 문구는 나중에 열 자리인데, 그때 의원 공통이 개인 것을 덮으면
        고쳐 둔 것이 조용히 묻힌다. 차례를 지금 못 박아 둔다.
        """
        clinic = await make_clinic()
        doctor = await make_staff(clinic, "k255-p", ["doctor"])
        staff = await make_staff(clinic, "k255-ps", ["staff"])
        await save_doctor_copy(clinic, None, SET_NAME, "의원 공통")
        await save_doctor_copy(clinic, doctor, SET_NAME, "담당 의사 것")
        visit = await make_visit_with_doctor(clinic, doctor, chart="KEY255-P1")
        await attach_confirmed_ocr(visit, staff.staff_id)

        response = await self.generate(visit, staff)

        assert response.status_code == 201, response.text
        sections = await self.sections_from_db(visit.visit_id)
        assert sections[GuideSectionKey.CAUTION].generated_body == "담당 의사 것"
