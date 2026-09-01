"""검사 기준선 — KEY-234, 와이어프레임 D2-4.

원문 주석: 「기준선 → D1 「나의 목표」의 남은 거리 계산에 쓰인다」.

**가장 크게 재는 것은 「비워 둘 수 있는가」다.** 원문: 「비워 두면 값과 추이만
표시하고 목표 대비 수치는 계산하지 않습니다」. 기준선은 검사기관과 나이에 따라
다르고, 모르는 채로 셈해 「목표까지 3 남았습니다」라고 말하는 것이 제일 나쁘다.
"""

from httpx import ASGITransport, AsyncClient
from tortoise.contrib.test import TestCase

from app.core.redis_client import get_redis
from app.core.utils.security import hash_password
from app.main import app
from app.models.catalog import LabBaseline
from app.models.staffs import Hospital, Staff
from app.services.lab_baselines import DEFAULT_BASELINES
from app.services.staff_auth import StaffSessionService
from app.tests.fakes import FakeRedis


def an_item(**over) -> dict:
    row = {
        "disease": "PCOS",
        "name": "월경 주기",
        "direction": "KEEP",
        "low": "21",
        "high": "35",
        "by_age": False,
        "keywords": "LMP, 월경, 주기",
        "unit": "일",
        "always_shown": True,
    }
    row.update(over)
    return row


class LabBaselineTestCase(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.redis = FakeRedis()
        app.dependency_overrides[get_redis] = lambda: self.redis

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        super().tearDown()

    async def a_staff(self, roles: list[str], login: str, clinic: Hospital | None = None, name: str = "박연") -> Staff:
        clinic = clinic or await Hospital.create(name=f"의원 {login}")
        return await Staff.create(
            hospital=clinic,
            login_id=login,
            password_hash=hash_password("pw"),
            name=name,
            roles=roles,
            must_change_password=False,
        )

    async def headers(self, staff: Staff) -> dict[str, str]:
        access, _ = await StaffSessionService(self.redis).start(staff)  # type: ignore[arg-type]
        return {"Authorization": f"Bearer {access}"}

    def client(self) -> AsyncClient:
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    async def fetch(self, staff: Staff, **params) -> dict:
        async with self.client() as client:
            response = await client.get("/api/v1/lab-baselines", headers=await self.headers(staff), params=params)
        assert response.status_code == 200, response.text
        return response.json()

    async def save(self, staff: Staff, items: list[dict], **params):
        async with self.client() as client:
            return await client.put(
                "/api/v1/lab-baselines",
                headers=await self.headers(staff),
                params=params,
                json={"items": items},
            )

    # ── 처음 열 때 ───────────────────────────────────────

    async def test_the_first_visit_lays_the_defaults(self) -> None:
        """**빈 화면을 보이면 의사가 열세 줄을 손으로 적어야 한다.**"""
        staff = await self.a_staff(["staff"], "seed")

        body = await self.fetch(staff)

        assert len(body["items"]) == len(DEFAULT_BASELINES) == 13
        assert body["items"][0]["name"] == "월경 주기", "차례도 원문대로다"

    async def test_opening_twice_does_not_double(self) -> None:
        staff = await self.a_staff(["staff"], "twice")

        await self.fetch(staff)
        await self.fetch(staff)

        assert await LabBaseline.all().count() == len(DEFAULT_BASELINES)

    async def test_the_defaults_match_what_the_wireframe_writes(self) -> None:
        staff = await self.a_staff(["staff"], "wire")

        rows = {item["name"]: item for item in (await self.fetch(staff))["items"]}

        assert rows["월경 주기"]["low"] == "21.00" and rows["월경 주기"]["high"] == "35.00"
        assert rows["혈색소 Hb"]["low"] == "12.00" and rows["혈색소 Hb"]["high"] is None, "「12.0 이상」"
        assert rows["간수치 AST/ALT"]["low"] is None and rows["간수치 AST/ALT"]["high"] == "40.00", "「40 미만」"
        assert rows["AMH"]["by_age"] is True, "「나이별」은 숫자 하나로 못 적는다"
        assert rows["LH / FSH"]["direction"] == "REFERENCE", "올리고 내릴 값이 아니다"
        assert rows["HbA1c"]["always_shown"] is False, "「＋ 항목 추가」에서 고른다"
        assert rows["BMI"]["unit"] == "", "단위가 없는 것도 있다"

    # ── 비워 두기 ────────────────────────────────────────

    async def test_a_baseline_can_be_left_empty(self) -> None:
        """원문: 「비워 두면 값과 추이만 표시하고 목표 대비 수치는 계산하지 않습니다」."""
        staff = await self.a_staff(["doctor"], "empty")

        response = await self.save(staff, [an_item(low=None, high=None)])

        assert response.status_code == 200
        saved = response.json()["items"][0]
        assert saved["low"] is None and saved["high"] is None

    async def test_by_age_clears_the_numbers(self) -> None:
        """나이별이면 숫자 하나로 못 적는다 — 남겨 두면 어느 쪽으로 셈할지 모른다."""
        staff = await self.a_staff(["doctor"], "byage")

        response = await self.save(staff, [an_item(by_age=True, low="21", high="35")])

        saved = response.json()["items"][0]
        assert saved["by_age"] is True and saved["low"] is None and saved["high"] is None

    async def test_a_backwards_range_is_refused(self) -> None:
        staff = await self.a_staff(["doctor"], "backwards")

        response = await self.save(staff, [an_item(low="35", high="21")])

        assert response.status_code == 422 and response.json()["code"] == "INVALID_RANGE"

    async def test_a_nameless_row_is_refused(self) -> None:
        staff = await self.a_staff(["doctor"], "noname")

        response = await self.save(staff, [an_item(name="  ")])

        assert response.status_code == 422 and response.json()["code"] == "EMPTY_NAME"

    async def test_the_same_item_twice_is_refused(self) -> None:
        staff = await self.a_staff(["doctor"], "dupe")

        response = await self.save(staff, [an_item(), an_item()])

        assert response.status_code == 422 and response.json()["code"] == "DUPLICATE_BASELINE"

    async def test_the_same_name_under_two_diseases_is_fine(self) -> None:
        """AMH 는 두 질환에 다 있다 — 원문이 그렇게 그린다."""
        staff = await self.a_staff(["doctor"], "amh")

        response = await self.save(staff, [an_item(name="AMH"), an_item(name="AMH", disease="ENDOMETRIOSIS")])

        assert response.status_code == 200 and len(response.json()["items"]) == 2

    # ── 한 판 통째로 ─────────────────────────────────────

    async def test_saving_replaces_the_whole_board(self) -> None:
        """줄마다 번호를 주고받으면 지운 줄을 놓쳐 유령이 남는다."""
        staff = await self.a_staff(["doctor"], "board")
        await self.fetch(staff)  # 기본 열세 줄이 깔린다

        response = await self.save(staff, [an_item(name="새 항목")])

        assert len(response.json()["items"]) == 1
        assert await LabBaseline.all().count() == 1

    async def test_the_order_is_kept(self) -> None:
        staff = await self.a_staff(["doctor"], "order")

        response = await self.save(staff, [an_item(name="셋째"), an_item(name="첫째"), an_item(name="둘째")])

        assert [row["name"] for row in response.json()["items"]] == ["셋째", "첫째", "둘째"]

    # ── 누구 기준 ────────────────────────────────────────

    async def test_the_picker_needs_the_doctors(self) -> None:
        """원문: 「「누구 기준」은 의사가 2인 이상일 때만 표시됩니다」."""
        clinic = await Hospital.create(name="도로시여성의원")
        staff = await self.a_staff(["staff"], "who", clinic)
        await self.a_staff(["doctor"], "who-1", clinic, name="박연")
        await self.a_staff(["doctor"], "who-2", clinic, name="김연우")

        body = await self.fetch(staff)

        assert [row["name"] for row in body["doctors"]] == ["박연", "김연우"]
        assert body["doctor_id"] is None, "기본은 의원 공통이다"

    async def test_a_doctor_without_a_board_of_their_own_sees_the_clinic_one(self) -> None:
        """**빈 화면을 띄우면 「이 의사에게는 기준이 없다」로 읽힌다** — 실제로는
        의원 공통이 쓰인다."""
        clinic = await Hospital.create(name="도로시여성의원")
        doctor = await self.a_staff(["doctor"], "own", clinic)
        await self.fetch(doctor)  # 의원 공통을 깐다

        body = await self.fetch(doctor, doctor_id=doctor.staff_id)

        assert len(body["items"]) == len(DEFAULT_BASELINES)

    async def test_a_doctor_board_does_not_touch_the_clinic_one(self) -> None:
        clinic = await Hospital.create(name="도로시여성의원")
        doctor = await self.a_staff(["doctor"], "mine", clinic)
        await self.fetch(doctor)

        await self.save(doctor, [an_item(name="나만의 항목")], doctor_id=doctor.staff_id)

        assert len((await self.fetch(doctor, doctor_id=doctor.staff_id))["items"]) == 1
        assert len((await self.fetch(doctor))["items"]) == len(DEFAULT_BASELINES)

    # ── 권한 · 격리 ──────────────────────────────────────

    async def test_staff_can_read_but_not_write(self) -> None:
        clinic = await Hospital.create(name="도로시여성의원")
        staff = await self.a_staff(["staff"], "readonly", clinic)

        assert (await self.fetch(staff))["items"], "판독 화면에 무엇이 뜰지 스탭도 알아야 한다"

        response = await self.save(staff, [an_item()])

        assert response.status_code == 403 and response.json()["code"] == "DOCTOR_ONLY"

    async def test_another_clinic_has_its_own_board(self) -> None:
        mine = await Hospital.create(name="도로시여성의원")
        theirs = await Hospital.create(name="다른의원")
        doctor = await self.a_staff(["doctor"], "scope-mine", mine)
        outsider = await self.a_staff(["doctor"], "scope-theirs", theirs)
        await self.save(doctor, [an_item(name="우리 항목")])

        body = await self.fetch(outsider)

        assert all(row["name"] != "우리 항목" for row in body["items"]), "남의 의원 기준이 새면 안 된다"
        assert len(body["items"]) == len(DEFAULT_BASELINES)

    async def test_signed_out_cannot_look(self) -> None:
        async with self.client() as client:
            response = await client.get("/api/v1/lab-baselines")
        assert response.status_code == 401
