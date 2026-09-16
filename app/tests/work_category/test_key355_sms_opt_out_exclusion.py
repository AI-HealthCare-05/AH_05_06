"""문자 수신 거부 환자를 업무 목록에서 제외한다 — KEY-355.

이희진(9/16) 결정: 거부한 환자는 안내문을 만들 이유 자체가 없다. 보완
탭에서만 빼면 판독 가지로 떨어져 「작성 중 · 문서 없음」이 될 뿐이라 자리만
옮기고 그대로 남는다 — 그래서 목록·counts 양쪽에서 완전히 뺀다.
"""

from datetime import date, datetime, time

from tortoise.contrib.test import TestCase
from tortoise.timezone import now

from app.core.time import DISPLAY_TIMEZONE
from app.dependencies.patient_access import ClinicalActor
from app.models.patients import Patient
from app.models.staffs import Hospital
from app.models.visits import GuideDocument, GuideStatus, Visit
from app.services.front_desk import FrontDeskService

TODAY = date(2026, 9, 16)
ACTOR = ClinicalActor(staff_id=355, hospital_id=1, roles=frozenset({"staff"}))


def kst(hhmm: str) -> datetime:
    hour, minute = (int(part) for part in hhmm.split(":"))
    return datetime.combine(TODAY, time(hour, minute), tzinfo=DISPLAY_TIMEZONE)


async def make_patient(hospital_id: int, number: str, *, opted_out: bool = False) -> Patient:
    return await Patient.create(
        hospital_id=hospital_id,
        hospital_patient_no=number,
        name=f"합성환자-{number}",
        birth_date=date(1990, 1, 1),
        phone="01012345678",
        sms_consent=not opted_out,
        sms_opted_out_at=now() if opted_out else None,
    )


async def make_visit(patient: Patient, *, guide_status: GuideStatus | None = None) -> Visit:
    visit = await Visit.create(hospital_id=patient.hospital_id, patient=patient, visited_at=kst("10:00"))
    if guide_status is not None:
        await GuideDocument.create(visit=visit, hospital_id=patient.hospital_id, status=guide_status)
    return visit


class TestOptedOutVisitsAreExcluded(TestCase):
    async def test_opted_out_visit_is_absent_from_both_items_and_counts(self) -> None:
        opted_out_patient = await make_patient(1, "OUT-1", opted_out=True)
        await make_visit(opted_out_patient)
        reachable_patient = await make_patient(1, "OK-1")
        await make_visit(reachable_patient)

        page = await FrontDeskService().list_visits(ACTOR, target_date=TODAY, categories=None, cursor=None, limit=50)

        assert [item.hospital_patient_no for item in page.items] == ["OK-1"]
        assert sum(page.counts.values()) == 1
        assert page.sms_opt_out_excluded == 1

    async def test_a_rejected_guide_for_an_opted_out_patient_is_still_excluded(self) -> None:
        """반려(NEEDS_ATTENTION 유발) 같은 다른 사유가 함께 있어도 뺀다."""
        patient = await make_patient(1, "OUT-2", opted_out=True)
        await make_visit(patient, guide_status=GuideStatus.APPROVAL_RETURNED)

        page = await FrontDeskService().list_visits(ACTOR, target_date=TODAY, categories=None, cursor=None, limit=50)

        assert page.items == []
        assert sum(page.counts.values()) == 0
        assert page.sms_opt_out_excluded == 1

    async def test_re_consenting_brings_the_visit_back(self) -> None:
        """수신 동의를 다시 받아 sms_opted_out_at이 비면 정상 파생으로 돌아온다."""
        patient = await make_patient(1, "OUT-3", opted_out=True)
        await make_visit(patient)

        before = await FrontDeskService().list_visits(ACTOR, target_date=TODAY, categories=None, cursor=None, limit=50)
        assert before.items == []

        patient.sms_opted_out_at = None
        await patient.save(update_fields=["sms_opted_out_at"])

        after = await FrontDeskService().list_visits(ACTOR, target_date=TODAY, categories=None, cursor=None, limit=50)
        assert [item.hospital_patient_no for item in after.items] == ["OUT-3"]
        assert after.sms_opt_out_excluded == 0

    async def test_counts_sum_always_matches_the_item_count(self) -> None:
        """인수조건 — counts 다섯 칸의 합 = 목록 줄 수."""
        await make_visit(await make_patient(1, "OUT-4", opted_out=True))
        await make_visit(await make_patient(1, "OK-2"))
        await make_visit(await make_patient(1, "OK-3"))

        page = await FrontDeskService().list_visits(ACTOR, target_date=TODAY, categories=None, cursor=None, limit=50)

        assert sum(page.counts.values()) == len(page.items)

    async def test_another_hospitals_opted_out_visit_does_not_count_here(self) -> None:
        """타 병원 진료가 목록·건수에 섞이지 않는다(load_signals의 hospital_id 이중 필터 회귀)."""
        await Hospital.create(hospital_id=2, name="다른 병원")
        other_hospital_patient = await make_patient(2, "OTHER-1", opted_out=True)
        await make_visit(other_hospital_patient)
        my_patient = await make_patient(1, "OK-4")
        await make_visit(my_patient)

        page = await FrontDeskService().list_visits(ACTOR, target_date=TODAY, categories=None, cursor=None, limit=50)

        assert [item.hospital_patient_no for item in page.items] == ["OK-4"]
        assert page.sms_opt_out_excluded == 0, "타 병원 수신거부 건이 이 병원 제외 건수에 섞였다"
