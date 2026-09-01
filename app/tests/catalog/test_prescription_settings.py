"""처방 설정 — KEY-234, 와이어프레임 D2-3.

처방 세트가 이름 하나뿐이었다. 의사가 정할 것들이 표에 없어서 「어느 처방에
무엇을 여쭐지」도 「소진 예정일을 어떻게 셈할지」도 코드에 박혀 있었다.

**`days_mode` 가 가장 무거운 값이다.** EMR 「총투」 칸의 「3」이 3통일 수도
3일일 수도 있는데 의원마다 다르다 — 소진 예정일과 소진 임박 문자가 이 값으로
셈해지므로, 틀리면 문자가 엉뚱한 날 간다.
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
    """설정 화면이 보내는 한 판. 검사마다 한 곳만 바꿔 쓴다."""
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

    async def a_set(self) -> PrescriptionSet:
        return await PrescriptionSet.create(name="자궁내막증 · 비잔 (계속)")

    # ── 읽기 ─────────────────────────────────────────────────────────

    async def test_staff_can_read_but_not_write(self) -> None:
        """**보는 것은 스탭도, 고치는 것은 의사만.**

        와이어프레임 D2-2 가 「의사 계정만 · 스탭은 볼 수만 있다」로 못박는다.
        이 값이 안내문과 문자 발송일을 정하므로 의료 판단에 걸린다. 스탭은
        판독 화면에서 처방을 고를 때 무엇이 딸려 있는지 알아야 한다.
        """
        row = await self.a_set()
        staff = await self.make_staff(["staff"])

        async with self.client() as client:
            headers = await self.sign_in(staff)
            got = await client.get(f"/api/v1/prescription-sets/{row.prescription_set_id}", headers=headers)
            put = await client.put(
                f"/api/v1/prescription-sets/{row.prescription_set_id}", json=a_plan(), headers=headers
            )

        assert got.status_code == 200, "스탭이 못 본다"
        assert put.status_code == 403, f"스탭이 고쳤다: {put.status_code}"

    async def test_an_unknown_set_is_not_found(self) -> None:
        """**읽을 때도 저장할 때도 404 다.**

        저장 쪽에서 안 막으면 없는 세트에 값을 쓰려다 500 으로 터진다 —
        화면은 「잠시 뒤 다시 시도해 주세요」를 띄우고, 다시 해도 같다.
        """
        doctor = await self.make_staff(["doctor"])
        async with self.client() as client:
            headers = await self.sign_in(doctor)
            got = await client.get("/api/v1/prescription-sets/999999", headers=headers)
            put = await client.put("/api/v1/prescription-sets/999999", json=a_plan(), headers=headers)

        assert got.status_code == 404
        assert put.status_code == 404, f"없는 세트에 저장했다: {put.status_code}"

    # ── 저장 ─────────────────────────────────────────────────────────

    async def test_a_doctor_saves_the_whole_plan(self) -> None:
        """**한 판을 통째로 담는다** — 약을 지우고 항목을 켜는 것이 한 번의 저장이다."""
        row = await self.a_set()
        doctor = await self.make_staff(["doctor"])

        async with self.client() as client:
            put = await client.put(
                f"/api/v1/prescription-sets/{row.prescription_set_id}",
                json=a_plan(),
                headers=await self.sign_in(doctor),
            )

        assert put.status_code == 200, put.text
        body = put.json()
        assert body["disease"] == "ENDOMETRIOSIS"
        assert body["phase"] == "CONTINUE"
        assert body["emr_code"] == "주의사항 비잔"
        assert body["drugs"] == [{"name": "비잔정 2mg", "frequency": "1일 1회", "note": "매일 같은 시간"}]
        assert body["check_items"] == ["DEPRESSION", "OSTEOPOROSIS"]

    async def test_saving_twice_does_not_pile_up(self) -> None:
        """**지우고 다시 넣는다.** 줄이 쌓이면 안내문에 같은 약이 두 번 적힌다."""
        row = await self.a_set()
        doctor = await self.make_staff(["doctor"])

        async with self.client() as client:
            headers = await self.sign_in(doctor)
            for _ in range(3):
                await client.put(f"/api/v1/prescription-sets/{row.prescription_set_id}", json=a_plan(), headers=headers)

        assert await PrescriptionSetDrug.filter(prescription_set_id=row.prescription_set_id).count() == 1
        assert await PrescriptionCheckItem.filter(prescription_set_id=row.prescription_set_id).count() == 2

    async def test_removing_a_drug_removes_the_row(self) -> None:
        """뺀 약은 사라진다 — 남으면 안내문이 안 내는 약을 적는다."""
        row = await self.a_set()
        doctor = await self.make_staff(["doctor"])

        async with self.client() as client:
            headers = await self.sign_in(doctor)
            await client.put(f"/api/v1/prescription-sets/{row.prescription_set_id}", json=a_plan(), headers=headers)
            after = await client.put(
                f"/api/v1/prescription-sets/{row.prescription_set_id}",
                json=a_plan(drugs=[], check_items=[]),
                headers=headers,
            )

        assert after.json()["drugs"] == []
        assert after.json()["check_items"] == []

    async def test_pack_mode_needs_days_per_pack(self) -> None:
        """**통으로 세는데 한 통이 며칠인지 모르면 소진일을 셈할 수 없다.**

        비워 둔 채 저장되면 소진 임박 문자가 영영 안 나가거나 엉뚱한 날 나간다.
        """
        row = await self.a_set()
        doctor = await self.make_staff(["doctor"])

        async with self.client() as client:
            headers = await self.sign_in(doctor)
            bad = await client.put(
                f"/api/v1/prescription-sets/{row.prescription_set_id}",
                json=a_plan(days_mode="PACK", days_per_pack=None),
                headers=headers,
            )
            good = await client.put(
                f"/api/v1/prescription-sets/{row.prescription_set_id}",
                json=a_plan(days_mode="PACK", days_per_pack=28),
                headers=headers,
            )

        assert bad.status_code == 422, f"한 통이 며칠인지 없이 저장됐다: {bad.status_code}"
        assert good.status_code == 200
        assert good.json()["days_per_pack"] == 28

    async def test_days_mode_clears_the_pack_size(self) -> None:
        """일수로 바꾸면 통 크기를 비운다 — 남겨 두면 어느 쪽으로 셈하는지 흐려진다."""
        row = await self.a_set()
        doctor = await self.make_staff(["doctor"])

        async with self.client() as client:
            headers = await self.sign_in(doctor)
            await client.put(
                f"/api/v1/prescription-sets/{row.prescription_set_id}",
                json=a_plan(days_mode="PACK", days_per_pack=28),
                headers=headers,
            )
            after = await client.put(
                f"/api/v1/prescription-sets/{row.prescription_set_id}",
                json=a_plan(days_mode="DAYS", days_per_pack=28),
                headers=headers,
            )

        assert after.json()["days_per_pack"] is None, "일수로 세는데 통 크기가 남았다"

    async def test_the_check_items_reach_the_list(self) -> None:
        """**설정에서 고른 항목이 판독 화면으로 간다** — 이것이 이 화면의 쓸모다."""
        row = await self.a_set()
        doctor = await self.make_staff(["doctor"])

        async with self.client() as client:
            headers = await self.sign_in(doctor)
            await client.put(
                f"/api/v1/prescription-sets/{row.prescription_set_id}",
                json=a_plan(check_items=["DIABETES"]),
                headers=headers,
            )
            listed = await client.get("/api/v1/prescription-sets", headers=headers)

        mine = [s for s in listed.json() if s["prescription_set_id"] == row.prescription_set_id][0]
        assert mine["check_items"] == ["DIABETES"], "설정에서 고른 것이 목록에 안 실린다"

    async def test_the_order_of_drugs_and_items_is_kept(self) -> None:
        """적은 차례가 화면 차례다 — 안내문에 적히는 차례이기도 하다."""
        row = await self.a_set()
        doctor = await self.make_staff(["doctor"])

        drugs = [
            {"name": "야즈정", "frequency": "1일 1회", "note": None},
            {"name": "메트포르민 500mg", "frequency": "1일 2회", "note": "식후"},
        ]
        items = ["PREGNANCY_PLAN", "HYPERTENSION", "DIABETES"]

        async with self.client() as client:
            got = await client.put(
                f"/api/v1/prescription-sets/{row.prescription_set_id}",
                json=a_plan(drugs=drugs, check_items=items),
                headers=await self.sign_in(doctor),
            )

        assert [d["name"] for d in got.json()["drugs"]] == ["야즈정", "메트포르민 500mg"]
        assert got.json()["check_items"] == items

    async def test_blank_text_becomes_nothing(self) -> None:
        """공백만 적은 것은 안 적은 것이다 — 「 」이 남으면 화면이 값이 있는 줄 안다."""
        row = await self.a_set()
        doctor = await self.make_staff(["doctor"])

        async with self.client() as client:
            got = await client.put(
                f"/api/v1/prescription-sets/{row.prescription_set_id}",
                json=a_plan(emr_code="   ", revisit_note="", drugs=[{"name": "  ", "frequency": None, "note": None}]),
                headers=await self.sign_in(doctor),
            )

        body = got.json()
        assert body["emr_code"] is None
        assert body["revisit_note"] is None
        assert body["drugs"] == [], "이름 없는 약이 담겼다"
