"""하루의 경계가 **의원 시간대 자정**인가 — KEY-181.

`visited_at` 열은 KST 벽시계를 담는다(`use_tz` 는 켜져 있지만 `timezone` 이
`Asia/Seoul` 이다). 그런데 질의 창을 만들 때 `.astimezone(UTC)` 로 바꿔 넘기고
있었다. 그러면 창이 아홉 시간 밀려 **하루가 15:00 ~ 다음날 15:00** 이 된다.

두 자리에서 서로 다른 모습으로 터졌다.

    접수대 목록      15:00 KST 이후 진료가 그날 목록에서 빠진다. 그리고 다음 날
                     목록에서는 `astimezone(KST).date()` 재확인이 걸러 내므로
                     **어느 날짜에도 안 뜬다**
    하루 한 건 규칙   저녁 진료 뒤 다음 날 아침 재진이 「이미 등록」으로 막힌다

시연이 오후면 그날 진료가 접수대에서 통째로 사라지는 자리라, 두 축을 각각
못 박는다. **한쪽만 재면 다른 쪽이 조용히 갈린다** — 실제로 티켓은 접수대만
알고 있었다.
"""

import unittest
from datetime import date, datetime, time, timedelta

from tortoise.contrib.test import TestCase

from app.core.api_errors import ApiError
from app.core.time import DISPLAY_TIMEZONE, clinic_day_window
from app.dependencies.patient_access import ClinicalActor
from app.dtos.visits import VisitCreateRequest
from app.models.patients import Patient
from app.models.staffs import Hospital
from app.models.visits import Visit
from app.services.front_desk import FrontDeskService
from app.services.visits import VisitService

#: 시연 날짜. 오후 진료가 사라지는 것을 처음 본 날이다.
DEMO_DAY = date(2026, 8, 27)
ACTOR = ClinicalActor(staff_id=181, hospital_id=1, roles=frozenset({"staff"}))


def kst(day: date, hhmm: str) -> datetime:
    hour, minute = (int(part) for part in hhmm.split(":"))
    return datetime.combine(day, time(hour, minute), tzinfo=DISPLAY_TIMEZONE)


async def make_patient(number: str) -> Patient:
    return await Patient.create(
        hospital_id=1,
        hospital_patient_no=number,
        name=f"합성환자-{number}",
        birth_date=date(1990, 8, 27),
        phone="01012345678",
        sms_consent=True,
    )


async def make_visit(patient: Patient, when: datetime) -> Visit:
    return await Visit.create(hospital_id=1, patient=patient, visited_at=when)


async def front_desk_ids(target: date) -> set[int]:
    page = await FrontDeskService().list_visits(ACTOR, target_date=target, categories=None, cursor=None, limit=50)
    return {row.visit_id for row in page.items}


class TestTheFrontDeskDayIsTheClinicDay(TestCase):
    """접수대 하루가 **KST 자정에서 자정까지**인가."""

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        await Hospital.create(hospital_id=1, name="합성의원181")

    async def test_morning_afternoon_and_night_all_show_on_the_same_day(self) -> None:
        """**이 검사가 이 일감의 이유다.**

        15:30 과 22:30 이 빠지던 자리다. 09:30 만 남으면 오후 시연에서 그날
        진료가 통째로 사라진다.
        """
        made = {}
        for index, hhmm in enumerate(("09:30", "15:30", "22:30")):
            patient = await make_patient(f"SYN-KEY181-{index}")
            visit = await make_visit(patient, kst(DEMO_DAY, hhmm))
            made[hhmm] = visit.visit_id

        seen = await front_desk_ids(DEMO_DAY)

        missing = sorted(hhmm for hhmm, visit_id in made.items() if visit_id not in seen)
        assert not missing, (
            f"{DEMO_DAY} 진료가 그날 접수대 목록에서 빠졌다: {missing}\n"
            "  창을 UTC 로 바꿔 넘기면 15:00 KST 에서 잘린다 (KEY-181)."
        )

    async def test_neither_day_borrows_the_other_days_visits(self) -> None:
        """빠지는 것만 재면 **전부 다 보여 주는 구현**이 만점을 받는다.

        그래서 이웃 날짜가 남의 것을 안 가져가는지도 함께 잰다.
        """
        patient = await make_patient("SYN-KEY181-NIGHT")
        visit = await make_visit(patient, kst(DEMO_DAY, "22:30"))

        for neighbour in (DEMO_DAY - timedelta(days=1), DEMO_DAY + timedelta(days=1)):
            assert visit.visit_id not in await front_desk_ids(neighbour), (
                f"{DEMO_DAY} 22:30 진료가 {neighbour} 목록에도 뜬다 — 하루가 겹친다."
            )
        assert visit.visit_id in await front_desk_ids(DEMO_DAY)

    async def test_the_seam_is_midnight_in_the_clinic_timezone(self) -> None:
        """경계를 **1분 사이로** 물린다.

        23:59 과 00:00 이 각자 제 날짜에만 있어야 한다. 창이 밀리면 둘 중
        하나가 이웃 날로 새거나 아예 사라진다.
        """
        last = await make_visit(await make_patient("SYN-KEY181-2359"), kst(DEMO_DAY, "23:59"))
        first = await make_visit(await make_patient("SYN-KEY181-0000"), kst(DEMO_DAY + timedelta(days=1), "00:00"))

        today = await front_desk_ids(DEMO_DAY)
        tomorrow = await front_desk_ids(DEMO_DAY + timedelta(days=1))

        assert last.visit_id in today and last.visit_id not in tomorrow, "23:59 이 제 날짜에 없다"
        assert first.visit_id in tomorrow and first.visit_id not in today, "00:00 이 제 날짜에 없다"


class TestOnePerDayCountsTheClinicDay(TestCase):
    """「한 환자에게 같은 날 진료 한 건」의 **하루**도 같은 자다.

    티켓은 접수대만 알고 있었다. 같은 뿌리에서 나온 두 번째 자리다.
    """

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        await Hospital.create(hospital_id=1, name="합성의원181")

    async def test_an_evening_visit_does_not_block_the_next_morning(self) -> None:
        """저녁에 온 환자를 **다음 날 아침에 접수할 수 있어야** 한다.

        창이 15:00 씩 밀리면 8/27 22:30 과 8/28 09:30 이 같은 창에 들어가,
        다른 날인데도 뒤엣것이 `409` 로 막힌다.
        """
        patient = await make_patient("SYN-KEY181-EVENING")
        service = VisitService()

        await service.create(ACTOR, patient.patient_id, VisitCreateRequest(visited_at=kst(DEMO_DAY, "22:30")))
        created = await service.create(
            ACTOR,
            patient.patient_id,
            VisitCreateRequest(visited_at=kst(DEMO_DAY + timedelta(days=1), "09:30")),
        )

        assert created.visit_id is not None

    async def test_two_visits_on_the_same_clinic_day_are_still_refused(self) -> None:
        """**느슨해지지 않았는가.** 막는 것만 걷어 내면 규칙 자체가 사라진다."""
        patient = await make_patient("SYN-KEY181-SAMEDAY")
        service = VisitService()

        await service.create(ACTOR, patient.patient_id, VisitCreateRequest(visited_at=kst(DEMO_DAY, "09:30")))

        try:
            await service.create(ACTOR, patient.patient_id, VisitCreateRequest(visited_at=kst(DEMO_DAY, "22:30")))
        except ApiError as error:
            assert error.code == "VISIT_ALREADY_REGISTERED", error.code
        else:
            raise AssertionError("같은 날 두 번째 진료가 그냥 들어갔다 — 규칙이 사라졌다")


class TestTheWindowKeepsItsTimezone(unittest.TestCase):
    """경계 값이 **시간대를 달고** 나오는가 — KEY-181.

    위 검사들은 SQL 을 거쳐 잰다. 그런데 asyncmy 의 `escape_datetime` 은
    tzinfo 를 무시하고 `.hour`·`.minute` 만 싣는다. 그래서 `clinic_day_window`
    가 **tzinfo 를 떼고 naive KST** 를 돌려줘도 오늘은 SQL 이 똑같아 위
    검사들이 전부 통과한다 — 실제로 확인했다.

    지금은 무해하지만, 저장을 UTC 로 정규화하는 날(KEY-181 의 갈래 ②) 그
    순간 조용히 깨진다. 그때 이 두 줄이 먼저 운다.
    """

    def test_both_edges_carry_the_clinic_timezone(self) -> None:
        day_start, day_end = clinic_day_window(date(2026, 8, 27))
        for label, edge in (("day_start", day_start), ("day_end", day_end)):
            with self.subTest(edge=label):
                self.assertIsNotNone(edge.tzinfo, f"{label} 이 naive 다 — 시간대를 달고 나와야 한다")
                self.assertEqual(
                    edge.utcoffset(),
                    datetime(2026, 8, 27, tzinfo=DISPLAY_TIMEZONE).utcoffset(),
                    f"{label} 이 의원 시간대가 아니다",
                )

    def test_it_is_local_midnight_to_local_midnight(self) -> None:
        day_start, day_end = clinic_day_window(date(2026, 8, 27))
        self.assertEqual((day_start.hour, day_start.minute, day_start.second), (0, 0, 0))
        self.assertEqual(day_start.date(), date(2026, 8, 27))
        self.assertEqual(day_end.date(), date(2026, 8, 28))
        self.assertEqual(day_end - day_start, timedelta(days=1))
