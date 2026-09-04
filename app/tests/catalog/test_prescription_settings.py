"""처방 설정 — KEY-234, 와이어프레임 D2-3.

처방 세트가 이름 하나뿐이었다. 의사가 정할 것들이 표에 없어서 「어느 처방에
무엇을 여쭐지」도 「소진 예정일을 어떻게 셈할지」도 코드에 박혀 있었다. 그
값들을 표로 옮기고 설정 화면이 읽게 했다.

**의원 하나를 보는 프로그램이다**(2026-09-02 회의). 처방 여덟은 그 의원의
것이고, 한 의원 안의 의사들이 모두 공통으로 쓴다. 그래서 「누구 것인가」를
묻지 않고 역할도 안 본다 — 같은 회의에서 설정 수정을 스탭에게도 열었다.

한동안 쓰기가 닫혀 있었다. 여러 의원이 한 표를 나눠 쓰는 모양이라 남의 의원
것까지 바뀌었기 때문이다(`#183` 리뷰, 2heej). 의원이 하나라는 것이 정해지면서
그 걱정이 범위 밖으로 갔다 — **고친 것이 아니라 범위가 줄어든 것이다.**
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

    # ── 쓰기 ─────────────────────────────────────────────────────────

    async def test_the_name_is_refused_loudly(self) -> None:
        """**이름은 못 바꾼다 — 소리 나게 막는다.**

        지난 진료기록이 그 이름으로 이 세트를 가리키고 있다(스냅샷 문자열).
        바꾸면 그 진료들의 안내문 문구가 조용히 떨어져 나간다.

        받아 놓고 무시하면 안 된다 — 「바꿔 달라 보냈는데 200 이 오고 안 바뀐」
        조용한 성공이 제일 나쁘다. `StrictModel` 의 `extra="forbid"` 가 튕긴다.
        """
        row = await self.a_furnished_set()
        staff = await self.make_staff(["staff"])
        was = row.name

        async with self.client() as client:
            answer = await client.put(
                f"/api/v1/prescription-sets/{row.prescription_set_id}",
                json=a_plan(name="자궁내막증 · 비잔 (유지)"),
                headers=await self.sign_in(staff),
            )

        # 422 가 아니다 — `ContractRoute` 가 400 봉투로 바꾼다(`core/api_errors.py`).
        assert answer.status_code == 400, answer.text
        assert answer.json()["code"] == "INVALID_REQUEST"
        await row.refresh_from_db()
        assert row.name == was, "튕겼는데 이름이 바뀌었다"

    async def test_everything_else_still_saves(self) -> None:
        """**이름만 잠갔다.** 진단·약·일수·확인 항목은 그대로 고쳐진다."""
        row = await self.a_furnished_set()
        staff = await self.make_staff(["staff"])

        async with self.client() as client:
            answer = await client.put(
                f"/api/v1/prescription-sets/{row.prescription_set_id}",
                json=a_plan(disease="PCOS", check_items=["DIABETES"]),
                headers=await self.sign_in(staff),
            )

        assert answer.status_code == 200, answer.text
        assert answer.json()["disease"] == "PCOS"
        assert answer.json()["check_items"] == ["DIABETES"]

    async def test_staff_can_write_too(self) -> None:
        """스탭도 고친다 — 역할은 안 본다."""
        row = await self.a_furnished_set()
        staff = await self.make_staff(["staff"])

        async with self.client() as client:
            answer = await client.put(
                f"/api/v1/prescription-sets/{row.prescription_set_id}",
                json=a_plan(days_mode="PACK", days_per_pack=28),
                headers=await self.sign_in(staff),
            )

        assert answer.status_code == 200, answer.text
        assert answer.json()["days_per_pack"] == 28

    async def test_pack_mode_still_needs_a_pack_size(self) -> None:
        """**한 통이 며칠인지 모르면 소진 예정일을 못 셈한다.**

        그 값으로 소진 임박 문자가 나갈 날이 정해지므로, 비운 채 저장되면
        문자가 엉뚱한 날 간다.
        """
        row = await self.a_furnished_set()
        staff = await self.make_staff(["staff"])

        async with self.client() as client:
            answer = await client.put(
                f"/api/v1/prescription-sets/{row.prescription_set_id}",
                json=a_plan(days_mode="PACK", days_per_pack=None),
                headers=await self.sign_in(staff),
            )

        assert answer.status_code == 422
        assert answer.json()["code"] == "DAYS_PER_PACK_REQUIRED"

    async def test_an_unknown_set_is_not_found_on_write(self) -> None:
        staff = await self.make_staff(["staff"])

        async with self.client() as client:
            answer = await client.put(
                "/api/v1/prescription-sets/999999",
                json=a_plan(),
                headers=await self.sign_in(staff),
            )

        assert answer.status_code == 404
        assert answer.json()["code"] == "PRESCRIPTION_SET_NOT_FOUND"

    async def test_a_long_drug_name_is_refused_not_crashed(self) -> None:
        """**표 한계를 넘으면 계약에서 막는다 — 500 이 아니라.**

        안 막으면 MySQL 이 `DataError` 를 던지는데 그것을 잡는 자리가 없어
        500 이 난다. 화면은 「잠시 후 다시 시도해 주세요」라고 하지만 몇 번을
        눌러도 같은 500 이고, **어느 칸이 문제인지 말해 주지 않는다.**
        EMR 에서 성분명을 통째로 붙여 넣으면 100자는 쉽게 넘는다.
        """
        row = await self.a_furnished_set()
        staff = await self.make_staff(["staff"])

        async with self.client() as client:
            answer = await client.put(
                f"/api/v1/prescription-sets/{row.prescription_set_id}",
                json=a_plan(drugs=[{"name": "가" * 101, "frequency": None, "note": None}]),
                headers=await self.sign_in(staff),
            )

        assert answer.status_code == 400, answer.text
        assert answer.json()["code"] == "INVALID_REQUEST"

    async def test_an_absurd_pack_size_is_refused(self) -> None:
        """`SmallIntField` 범위를 넘으면 같은 자리에서 500 이 난다."""
        row = await self.a_furnished_set()
        staff = await self.make_staff(["staff"])

        async with self.client() as client:
            answer = await client.put(
                f"/api/v1/prescription-sets/{row.prescription_set_id}",
                json=a_plan(days_mode="PACK", days_per_pack=99999),
                headers=await self.sign_in(staff),
            )

        assert answer.status_code == 400, answer.text
