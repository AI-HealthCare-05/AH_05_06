"""처방 설정 — KEY-234, 와이어프레임 D2-3.

처방 세트가 이름 하나뿐이었다. 의사가 정할 것들이 표에 없어서 「어느 처방에
무엇을 여쭐지」도 「소진 예정일을 어떻게 셈할지」도 코드에 박혀 있었다. 그
값들을 표로 옮기고 설정 화면이 읽게 했다.

**고치는 길은 아직 열지 않았다.** `prescription_set` 에는 `hospital_id` 가
없다 — 여덟 처방 유형을 전 의원이 함께 쓴다. 한동안 역할(의사)만 확인하고
`PUT` 을 열어 두었는데, 그러면 어느 의원 의사든 다른 모든 의원의 질환 분류 ·
총투 해석 · 소진 예정일 셈법을 바꿀 수 있다. 그 값들이 안내문 문구와 문자
발송일을 정한다. 2heej 님이 `#183` 리뷰에서 찾아 주셨다.

표를 의원별로 가르는 것이 옳은 해결이고 별도 일감이다. 이 파일은 그때까지
**읽기만 되고 쓰기는 닫혀 있다**는 것을 못 박는다.
"""

from httpx import ASGITransport, AsyncClient
from tortoise.contrib.test import TestCase

from app.core.redis_client import get_redis
from app.core.utils.security import hash_password
from app.main import app
from app.models.catalog import PrescriptionCheckItem, PrescriptionSet, PrescriptionSetDrug
from app.models.staffs import Hospital, Staff
from app.services.staff_auth import StaffSessionService
from app.tests.fakes import FakeRedis


def a_plan(**over) -> dict:
    """설정 화면이 보내던 한 판. 쓰기가 닫힌 것을 재는 데 쓴다."""
    plan = {
        "name": "자궁내막증 · 비잔 (계속)",
        "disease": "ENDOMETRIOSIS",
        "phase": "CONTINUE",
        "days_mode": "DAYS",
        "days_per_pack": None,
        "emr_code": "주의사항 비잔",
        "revisit_note": "3개월 복용 후 내원",
        "check_d15_on": True,
        "check_d30_on": False,
        "run_out_on": True,
        "run_out_before_days": 3,
        "drugs": [{"name": "비잔정 2mg", "frequency": "1일 1회", "note": "매일 같은 시간"}],
        "check_items": ["DEPRESSION", "OSTEOPOROSIS"],
    }
    plan.update(over)
    return plan


class PrescriptionSettingsTestCase(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.redis = FakeRedis()
        app.dependency_overrides[get_redis] = lambda: self.redis

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        super().tearDown()

    async def make_staff(self, roles: list[str]) -> Staff:
        hospital = await Hospital.create(name=f"여성의원 {'-'.join(roles)}")
        return await Staff.create(
            hospital=hospital,
            login_id=f"set-{'-'.join(roles)}",
            password_hash=hash_password("pw"),
            name="테스트",
            roles=roles,
            must_change_password=False,
        )

    async def sign_in(self, staff: Staff) -> dict[str, str]:
        access, _ = await StaffSessionService(self.redis).start(staff)  # type: ignore[arg-type]
        return {"Authorization": f"Bearer {access}"}

    def client(self) -> AsyncClient:
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    async def a_furnished_set(self) -> PrescriptionSet:
        """약과 확인 항목이 딸린 세트 하나. **표에 직접 넣는다** — 이 표를
        채우는 API 가 없으므로(쓰기가 닫혔다) 씨앗 마이그레이션과 같은 길이다."""
        row = await PrescriptionSet.create(
            name="자궁내막증 · 비잔 (계속)",
            disease="ENDOMETRIOSIS",
            phase="CONTINUE",
            days_mode="PACK",
            days_per_pack=28,
            emr_code="주의사항 비잔",
            revisit_note="3개월 복용 후 내원",
        )
        await PrescriptionSetDrug.create(
            prescription_set=row, name="비잔정 2mg", frequency="1일 1회", note="매일 같은 시간", position=0
        )
        await PrescriptionSetDrug.create(prescription_set=row, name="철분제", position=1)
        await PrescriptionCheckItem.create(prescription_set=row, item_key="DEPRESSION", position=0)
        await PrescriptionCheckItem.create(prescription_set=row, item_key="OSTEOPOROSIS", position=1)
        return row

    # ── 읽기 ─────────────────────────────────────────────────────────

    async def test_staff_can_read_the_plan(self) -> None:
        """**보는 것은 스탭도 된다.** 판독 화면에서 처방을 고를 때 무엇이
        딸려 있는지 알아야 한다."""
        row = await self.a_furnished_set()
        staff = await self.make_staff(["staff"])

        async with self.client() as client:
            got = await client.get(
                f"/api/v1/prescription-sets/{row.prescription_set_id}", headers=await self.sign_in(staff)
            )

        assert got.status_code == 200, got.text
        body = got.json()
        assert [drug["name"] for drug in body["drugs"]] == ["비잔정 2mg", "철분제"], "차례가 `position` 대로다"
        assert body["check_items"] == ["DEPRESSION", "OSTEOPOROSIS"]

    async def test_the_pack_size_comes_along(self) -> None:
        """**`days_mode` 가 가장 무거운 값이다.** EMR 「총투」의 「3」이 3통일
        수도 3일일 수도 있는데 의원마다 다르다 — 소진 예정일과 소진 임박
        문자가 이 값으로 셈해지므로, 틀리면 문자가 엉뚱한 날 간다."""
        row = await self.a_furnished_set()
        doctor = await self.make_staff(["doctor"])

        async with self.client() as client:
            got = await client.get(
                f"/api/v1/prescription-sets/{row.prescription_set_id}", headers=await self.sign_in(doctor)
            )

        body = got.json()
        assert body["days_mode"] == "PACK" and body["days_per_pack"] == 28

    async def test_an_unknown_set_is_not_found(self) -> None:
        doctor = await self.make_staff(["doctor"])

        async with self.client() as client:
            got = await client.get("/api/v1/prescription-sets/999999", headers=await self.sign_in(doctor))

        assert got.status_code == 404
        assert got.json()["code"] == "PRESCRIPTION_SET_NOT_FOUND"

    # ── 쓰기는 닫혀 있다 ─────────────────────────────────────────────

    async def test_nobody_can_write_the_shared_catalog(self) -> None:
        """**의사도 못 고친다.** 역할이 문제가 아니라 표가 전 의원 공용인
        것이 문제다 — `prescription_set` 에는 `hospital_id` 가 없다.

        의사에게만 열어 두면 「우리 의원 설정」처럼 보이는데 실제로는 모든
        의원이 함께 쓰는 값이 바뀐다. 그래서 길 자체를 닫는다.
        """
        row = await self.a_furnished_set()
        doctor = await self.make_staff(["doctor"])

        async with self.client() as client:
            put = await client.put(
                f"/api/v1/prescription-sets/{row.prescription_set_id}",
                json=a_plan(),
                headers=await self.sign_in(doctor),
            )

        assert put.status_code == 405, f"쓰기가 아직 열려 있다: {put.status_code}"

    async def test_the_write_did_not_move_to_another_verb(self) -> None:
        """`PUT` 만 걷고 `PATCH`·`POST` 로 옮겨 두면 막은 것이 아니다."""
        row = await self.a_furnished_set()
        doctor = await self.make_staff(["doctor"])
        at = f"/api/v1/prescription-sets/{row.prescription_set_id}"

        async with self.client() as client:
            headers = await self.sign_in(doctor)
            answers = {
                verb: (await client.request(verb, at, json=a_plan(), headers=headers)).status_code
                for verb in ("PUT", "PATCH", "POST", "DELETE")
            }

        assert all(code == 405 for code in answers.values()), answers

    async def test_the_catalog_is_untouched_after_a_refused_write(self) -> None:
        """막았다고 말만 하고 반쪽이 들어가면 더 나쁘다."""
        row = await self.a_furnished_set()
        doctor = await self.make_staff(["doctor"])

        async with self.client() as client:
            await client.put(
                f"/api/v1/prescription-sets/{row.prescription_set_id}",
                json=a_plan(name="바뀐 이름", drugs=[], check_items=[]),
                headers=await self.sign_in(doctor),
            )

        await row.refresh_from_db()
        assert row.name == "자궁내막증 · 비잔 (계속)"
        assert await PrescriptionSetDrug.filter(prescription_set_id=row.prescription_set_id).count() == 2
        assert await PrescriptionCheckItem.filter(prescription_set_id=row.prescription_set_id).count() == 2
