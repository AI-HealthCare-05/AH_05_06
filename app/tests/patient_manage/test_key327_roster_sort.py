"""환자 관리 표의 **차례** — KEY-327.

표가 등록 **과거순**으로 섰다. `order_by("patient_id")` 오름차순이라, 방금
등록한 환자가 맨 뒤 쪽에 있었다 — 등록하고 바로 확인하려면 마지막 쪽까지
넘겨야 했다.

여기서 재는 것은 셋이다.

  ① 기본이 **최근 등록순**이다
  ② 차트번호로도 세울 수 있고, **자리수가 섞여도 숫자처럼** 선다
  ③ 이어 보기(`cursor`)는 **등록 오름차순 하나만** 탄다

③ 이 규칙인 까닭: 커서는 `patient_id > cursor` 로 앞으로만 간다. 다른 차례를
얹으면 건너뛴 환자가 생기고, 그것은 화면에서야 드러난다.

**정렬은 서버가 한다.** 화면이 받은 쪽만 다시 세우면 그 쪽 안에서만 맞고 쪽을
넘기면 겹치거나 빠진다 — 그래서 이 파일은 전부 종점을 통해 잰다.
"""

from datetime import UTC, datetime, timedelta

from httpx import ASGITransport, AsyncClient
from tortoise.expressions import Q

from app.main import app
from app.models.patients import Patient
from app.models.visits import Visit
from app.services.staff_auth import StaffSessionService
from app.tests.patient_manage.test_patient_table import PatientTableBase

URL = "/api/v1/patients"


class RosterSortTestCase(PatientTableBase):
    async def signed_in(self, login: str = "sorter"):
        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["staff"], login)
        access, _ = await StaffSessionService(self.redis).start(staff)  # type: ignore[arg-type]
        return clinic, {"Authorization": f"Bearer {access}"}

    async def ask(self, headers: dict[str, str], **params) -> list[str]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            answer = await client.get(URL, headers=headers, params=params)
        assert answer.status_code == 200, answer.text
        return [row["hospital_patient_no"] for row in answer.json()["items"]]


class TestTheNewestRegisteredComesFirst(RosterSortTestCase):
    async def test_the_default_is_the_newest(self) -> None:
        """인수조건 — 기본으로 가장 최근 등록한 환자부터 선다."""
        clinic, headers = await self.signed_in()
        for index in range(3):
            await self.a_patient(clinic, name=f"조하늘{index}", chart=f"1000{index}")

        assert await self.ask(headers) == ["10002", "10001", "10000"]

    async def test_the_old_way_is_still_reachable(self) -> None:
        clinic, headers = await self.signed_in()
        for index in range(3):
            await self.a_patient(clinic, name=f"조하늘{index}", chart=f"1000{index}")

        assert await self.ask(headers, sort="registered_asc") == ["10000", "10001", "10002"]

    async def test_paging_does_not_repeat_or_skip(self) -> None:
        """**쪽 안에서만 맞으면 안 된다.** 화면이 받은 쪽을 다시 세우면 그렇게 된다."""
        clinic, headers = await self.signed_in()
        for index in range(5):
            await self.a_patient(clinic, name=f"조하늘{index}", chart=f"2000{index}")

        walked = await self.ask(headers, limit=2) + await self.ask(headers, limit=2, offset=2)
        walked += await self.ask(headers, limit=2, offset=4)

        assert walked == ["20004", "20003", "20002", "20001", "20000"]


class TestTheChartNumberSortsLikeANumber(RosterSortTestCase):
    """🚩 차트번호는 **글자열**이다 — `CharField(50)` 이고 형식 규칙이 없다.

    글자로만 세우면 `10` 이 `7` 보다 앞에 선다. 지금 자료가 다섯 자리로
    채워져 있어 안 드러날 뿐, 의원이 `7` 을 그대로 넣는 순간 표가 뒤집힌다.
    """

    CHARTS = ("7", "10", "9", "09948", "100")

    async def a_clinic_with_mixed_charts(self):
        clinic, headers = await self.signed_in()
        for index, chart in enumerate(self.CHARTS):
            await self.a_patient(clinic, name=f"조하늘{index}", chart=chart)
        return headers

    async def test_short_numbers_come_before_long_ones(self) -> None:
        headers = await self.a_clinic_with_mixed_charts()

        assert await self.ask(headers, sort="chart_asc") == ["7", "9", "10", "100", "09948"]

    async def test_the_other_way_is_the_exact_mirror(self) -> None:
        headers = await self.a_clinic_with_mixed_charts()

        rising = await self.ask(headers, sort="chart_asc")
        falling = await self.ask(headers, sort="chart_desc")

        assert falling == list(reversed(rising)), f"오름·내림이 서로의 거울이 아니다 — {rising} · {falling}"


class TestTheStampOnTheScreenIsTheKey(RosterSortTestCase):
    """**표가 보여 주는 그 날짜로 센다.**

    「등록 ▼」라고 써 놓고 다른 열쇠로 세우면 날짜가 오르락내리락해서 화면이
    고장난 것처럼 보인다. 보여 주는 값과 세우는 열쇠는 같아야 한다.
    """

    async def test_an_old_stamp_sinks_even_if_it_was_added_last(self) -> None:
        """옛 날짜를 달고 들어온 자료는 그 날짜 자리에 선다 — **날짜가 기준이다.**"""
        clinic, headers = await self.signed_in()
        for index in range(3):
            await self.a_patient(clinic, name=f"조하늘{index}", chart=f"3000{index}")
        #: 마지막에 만든 줄에 옛 날짜를 단다 — 옮겨 온 자료가 그렇다.
        newest = await Patient.filter(hospital_id=clinic.hospital_id).order_by("-patient_id").first()
        assert newest is not None
        await Patient.filter(patient_id=newest.patient_id).update(created_at="2020-01-01 01:00:00")

        assert await self.ask(headers) == ["30001", "30000", "30002"], (
            "등록일이 아니라 다른 열쇠로 세운다 — 「등록 ▼」인데 날짜가 뒤섞인다"
        )

    async def test_the_same_instant_still_has_one_answer(self) -> None:
        """같은 초에 등록한 둘이 있어도 차례가 하나다 — 번호로 갈라 주기 때문이다."""
        clinic, headers = await self.signed_in()
        for index in range(4):
            await self.a_patient(clinic, name=f"조하늘{index}", chart=f"3100{index}")
        await Patient.filter(hospital_id=clinic.hospital_id).update(created_at="2026-09-11 01:00:00")

        answers = {tuple(await self.ask(headers)) for _ in range(3)}

        assert len(answers) == 1, f"같은 물음에 다른 차례를 준다 — {answers}"
        assert answers.pop() == ("31003", "31002", "31001", "31000")


class TestTheLastVisitCanSortToo(RosterSortTestCase):
    """마지막 진료는 **다른 표에 있다** — 그 환자의 가장 늦은 진료를 끌어와 센다.

    한 번도 안 온 환자는 값이 없다. `NULL` 을 가장 작게 보므로 **최근순에서는
    맨 뒤, 오래된순에서는 맨 앞**에 선다 — 둘 다 「가장 오래 안 온 쪽」이라
    뜻이 맞는다.
    """

    async def a_clinic_with_visits(self):
        clinic, headers = await self.signed_in()
        #: 사흘 전 · 어제 · 열흘 전에 온 셋, 그리고 **한 번도 안 온** 하나
        await self.a_patient(clinic, name="조하늘0", chart="70000", visited_days_ago=3)
        await self.a_patient(clinic, name="조하늘1", chart="70001", visited_days_ago=1)
        await self.a_patient(clinic, name="조하늘2", chart="70002", visited_days_ago=10)
        await self.a_patient(clinic, name="조하늘3", chart="70003", visited_days_ago=None)
        return headers

    async def test_the_most_recent_visit_comes_first(self) -> None:
        headers = await self.a_clinic_with_visits()

        assert await self.ask(headers, sort="visited_desc") == ["70001", "70000", "70002", "70003"], (
            "마지막 진료 최근순이 아니다 — 한 번도 안 온 환자는 맨 뒤다"
        )

    async def test_the_other_way_puts_the_never_seen_first(self) -> None:
        headers = await self.a_clinic_with_visits()

        assert await self.ask(headers, sort="visited_asc") == ["70003", "70002", "70000", "70001"]

    async def test_only_that_patients_own_visits_count(self) -> None:
        """**다른 환자의 진료를 끌어오면 안 된다** — 표와 차례가 어긋난다."""
        headers = await self.a_clinic_with_visits()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            answer = await client.get(URL, headers=headers, params={"sort": "visited_desc"})
        rows = answer.json()["items"]

        for row in rows:
            latest = row["latest_visit"]
            if row["hospital_patient_no"] == "70003":
                assert latest is None, "한 번도 안 온 환자에게 진료가 붙었다"
            else:
                assert latest is not None, f"{row['hospital_patient_no']} 의 진료가 사라졌다"

    async def test_nobody_is_lost_or_doubled(self) -> None:
        """진료 표를 이어 붙이면 **환자가 늘어날 수 있다** — 한 사람이 여러 번 온다."""
        clinic, headers = await self.signed_in()
        patient = await self.a_patient(clinic, name="여러번", chart="71000", visited_days_ago=5)
        for days in (1, 3):
            await Visit.create(
                hospital_id=clinic.hospital_id,
                patient=patient,
                visited_at=datetime.now(UTC) - timedelta(days=days),
            )

        assert await self.ask(headers, sort="visited_desc") == ["71000"], "한 사람이 여러 줄로 나온다"


class TestTheCursorOnlyWalksForward(RosterSortTestCase):
    async def test_asking_another_order_with_a_cursor_is_refused(self) -> None:
        """인수조건 — `cursor` 와 `id_asc` 아닌 `sort` 를 함께 보내면 400 이다."""
        _, headers = await self.signed_in()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            refused = await client.get(URL, headers=headers, params={"cursor": "1", "sort": "chart_asc"})

        assert refused.status_code == 400, refused.text
        assert refused.json()["code"] == "INVALID_REQUEST"
        assert {item["field"] for item in refused.json()["field_errors"]} == {"sort"}

    async def test_the_order_the_cursor_does_walk_is_allowed(self) -> None:
        """등록 화면의 찾기가 보내는 그 모양이다 — 막히면 그 화면이 죽는다."""
        clinic, headers = await self.signed_in()
        for index in range(3):
            await self.a_patient(clinic, name=f"조하늘{index}", chart=f"4000{index}")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            head = await client.get(URL, headers=headers, params={"limit": 2, "sort": "id_asc"})
            assert head.status_code == 200, head.text
            tail = await client.get(
                URL,
                headers=headers,
                params={"limit": 2, "sort": "id_asc", "cursor": head.json()["page"]["next_cursor"]},
            )

        assert tail.status_code == 200, tail.text
        walked = [row["hospital_patient_no"] for row in head.json()["items"]]
        walked += [row["hospital_patient_no"] for row in tail.json()["items"]]
        assert walked == ["40000", "40001", "40002"], "이어 보기가 겹치거나 건너뛴다"


class TestTheCursorAndTheOrderShareOneKey(RosterSortTestCase):
    """이어 보기는 `patient_id >` 로 거른다. **세우는 열쇠도 같아야 한다.**

    둘이 갈리면 거름에서 잘린 사람이 영영 안 나오거나 이미 본 사람이 다시
    나온다 — 그리고 그것은 쪽을 넘겨 본 사람만 안다.
    """

    async def test_everyone_shows_up_exactly_once_even_with_old_stamps(self) -> None:
        clinic, headers = await self.signed_in()
        for index in range(3):
            await self.a_patient(clinic, name=f"조하늘{index}", chart=f"6000{index}")
        #: 시각을 번호와 어긋나게 흔든다 — 옮겨 온 자료가 그렇다.
        rows = await Patient.filter(hospital_id=clinic.hospital_id).order_by("patient_id")
        for patient, when in zip(
            rows, ("2026-01-01 01:00:00", "2026-03-01 01:00:00", "2026-02-01 01:00:00"), strict=True
        ):
            await Patient.filter(patient_id=patient.patient_id).update(created_at=when)

        walking: dict[str, str | int] = {"limit": 2, "sort": "id_asc"}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            head = await client.get(URL, headers=headers, params=walking)
            assert head.status_code == 200, head.text
            tail = await client.get(
                URL, headers=headers, params={**walking, "cursor": head.json()["page"]["next_cursor"]}
            )

        assert tail.status_code == 200, tail.text
        walked = [row["hospital_patient_no"] for row in head.json()["items"]]
        walked += [row["hospital_patient_no"] for row in tail.json()["items"]]

        assert walked == ["60000", "60001", "60002"], f"이어 보기가 누구를 빠뜨리거나 두 번 보여 준다 — {walked}"


class TestTheHospitalFenceStillHolds(RosterSortTestCase):
    async def test_another_clinics_patients_never_appear(self) -> None:
        """차례를 바꾸는 김에 울타리가 새면 안 된다."""
        clinic, headers = await self.signed_in()
        await self.a_patient(clinic, name="우리환자", chart="50001")
        neighbour = await self.a_clinic("옆동네의원")
        await self.a_patient(neighbour, name="옆집환자", chart="99999")

        for order in (
            "registered_desc",
            "registered_asc",
            "chart_asc",
            "chart_desc",
            "visited_desc",
            "visited_asc",
            "id_asc",
        ):
            assert await self.ask(headers, sort=order) == ["50001"], f"{order} 에서 옆 의원이 샌다"
        assert await Patient.filter(Q(hospital_id=neighbour.hospital_id)).count() == 1, "검사가 헛돈다"
