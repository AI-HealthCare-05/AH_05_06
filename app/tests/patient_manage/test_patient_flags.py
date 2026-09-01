"""이탈 배지 — KEY-234, 와이어프레임 S2-1 「★ 이탈을 잡는 자리」.

원문이 세 가지를 든다.

    ⚠ 3회 연속 미열람   확인 문자를 세 번 보냈는데 안내를 한 번도 안 열었다
    ⚠ 복약 중단 응답     확인 링크에서 그만 먹는다고 답했다
    ⚠ 소진 후 7일 경과   약이 떨어진 지 이레가 지났는데 다시 안 왔다

**배지는 「이 환자를 챙기라」는 말이다.** 근거가 없는데 붙이면 챙길 일이 없는
환자를 부르게 되고, 몇 번 헛걸음하면 배지 전체를 안 믿게 된다. 그래서 여기서
가장 많이 재는 것은 「붙는 자리」가 아니라 **「안 붙는 자리」** 다.
"""

from datetime import date, timedelta

from tortoise.contrib.test import TestCase

from app.models.patients import Patient, PatientGender
from app.models.staffs import Hospital
from app.models.visits import (
    CheckIn,
    CheckInMedication,
    GuideDocument,
    Visit,
)
from app.services.patient_flags import (
    RUN_OUT_GRACE,
    UNREAD_STREAK,
    FlagInput,
    PatientFlag,
    flags_of,
    stopped_dosing,
)

TODAY = date(2026, 9, 1)


def an_input(**over) -> FlagInput:
    values = {"checks_sent": 0, "viewed": False, "runs_out_on": None}
    values.update(over)
    return FlagInput(**values)


class FlagRuleTestCase(TestCase):
    # ── 3회 연속 미열람 ──────────────────────────────────

    def test_three_unread_checks_raise_the_badge(self) -> None:
        found = flags_of(an_input(checks_sent=UNREAD_STREAK, viewed=False), TODAY)

        assert found == [PatientFlag.UNREAD_STREAK]

    def test_two_is_not_a_streak(self) -> None:
        assert flags_of(an_input(checks_sent=UNREAD_STREAK - 1, viewed=False), TODAY) == []

    def test_opening_once_clears_it(self) -> None:
        """세 번 보냈어도 한 번 열었으면 연속이 아니다."""
        assert flags_of(an_input(checks_sent=5, viewed=True), TODAY) == []

    # ── 소진 후 7일 경과 ────────────────────────────────

    def test_a_week_past_the_run_out_raises_the_badge(self) -> None:
        ran_out = TODAY - timedelta(days=RUN_OUT_GRACE + 1)

        assert flags_of(an_input(runs_out_on=ran_out), TODAY) == [PatientFlag.RUN_OUT_OVERDUE]

    def test_the_grace_day_itself_is_not_late_yet(self) -> None:
        """이레째 되는 날은 아직 아니다 — 하루라도 일찍 부르면 헛걸음이 는다."""
        assert flags_of(an_input(runs_out_on=TODAY - timedelta(days=RUN_OUT_GRACE)), TODAY) == []

    def test_an_unknown_course_length_raises_nothing(self) -> None:
        """**모르면 붙이지 않는다.** 처방일수가 없으면 소진일도 없다."""
        assert flags_of(an_input(runs_out_on=None), TODAY) == []

    def test_two_badges_can_land_together(self) -> None:
        found = flags_of(an_input(checks_sent=UNREAD_STREAK, runs_out_on=TODAY - timedelta(days=30)), TODAY)

        assert found == [PatientFlag.UNREAD_STREAK, PatientFlag.RUN_OUT_OVERDUE]

    def test_a_quiet_patient_gets_no_badge(self) -> None:
        assert flags_of(an_input(), TODAY) == [], "빈 목록이 정상이다 — 챙길 일이 없다는 뜻이다"


class StoppedDosingTestCase(TestCase):
    """**한 번 「담을 표가 없다」고 잘못 적었던 자리다.**

    `check_in` 이 KEY-151 부터 있고 다섯 답 중 둘이 중단인데, 없다고 단정하고
    늘 빈 집합을 돌려주게 두었었다. 검사가 있었으면 그때 걸렸다.
    """

    async def a_visit(self, hospital: Hospital, name: str, chart: str) -> tuple[Patient, GuideDocument]:
        patient = await Patient.create(
            hospital_id=hospital.hospital_id,
            hospital_patient_no=chart,
            name=name,
            birth_date=date(1992, 5, 20),
            gender=PatientGender.FEMALE,
            phone="01044524085",
        )
        visit = await Visit.create(
            hospital_id=hospital.hospital_id,
            patient=patient,
            visited_at=f"{TODAY.isoformat()}T09:00:00+09:00",
        )
        document = await GuideDocument.create(hospital_id=hospital.hospital_id, visit=visit)
        return patient, document

    async def test_both_kinds_of_stopping_count(self) -> None:
        hospital = await Hospital.create(name="도로시여성의원")
        answers = {
            "부작용": CheckInMedication.STOPPED_SIDE_EFFECT,
            "좋아짐": CheckInMedication.STOPPED_IMPROVED,
        }
        latest = {}
        for index, (name, answer) in enumerate(answers.items()):
            patient, document = await self.a_visit(hospital, name, f"CHK{index}")
            await CheckIn.create(guide_document=document, medication=answer)
            latest[patient.patient_id] = await Visit.get(visit_id=document.visit_id)

        found = await stopped_dosing(latest)

        assert found == set(latest), "좋아져서 끊은 것도 다음 진료에서 확인할 일이다"

    async def test_still_taking_is_not_stopping(self) -> None:
        hospital = await Hospital.create(name="도로시여성의원")
        latest = {}
        for index, answer in enumerate(
            (CheckInMedication.TAKING, CheckInMedication.UNCOMFORTABLE, CheckInMedication.MISSING)
        ):
            patient, document = await self.a_visit(hospital, f"환자{index}", f"KEEP{index}")
            await CheckIn.create(guide_document=document, medication=answer)
            latest[patient.patient_id] = await Visit.get(visit_id=document.visit_id)

        assert await stopped_dosing(latest) == set(), "불편하다·걸렀다는 중단이 아니다"

    async def test_no_answer_is_not_stopping(self) -> None:
        hospital = await Hospital.create(name="도로시여성의원")
        patient, document = await self.a_visit(hospital, "무응답", "NONE1")
        latest = {patient.patient_id: await Visit.get(visit_id=document.visit_id)}

        assert await stopped_dosing(latest) == set(), "안 답한 것과 그만둔 것은 다르다"

    async def test_nothing_to_ask_about(self) -> None:
        assert await stopped_dosing({}) == set()
