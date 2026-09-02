"""약속처방 목록 — KEY-234.

의사가 설정에서 정해 두는 처방 세트다. 판독 확인 화면(S1-6)의 「처방」 칸이
이 목록에서 고른다 — 판독이 읽은 약 이름을 그대로 쓰지 않는다.

**자유 입력이면 안 되는 이유**가 이 API 의 존재 이유다. 이름을 고르면 그
세트에 묶인 주의 문구(`DrugCautionContent`)가 안내문에 붙는데, 「비잔」과
「비잔정」이 다른 값으로 들어오면 붙일 문구를 못 찾는다.
"""

from pathlib import Path

from httpx import ASGITransport, AsyncClient
from tortoise.contrib.test import TestCase

from app.core.redis_client import get_redis
from app.core.utils.security import hash_password
from app.main import app
from app.models.catalog import PrescriptionSet
from app.models.staffs import Hospital, Staff
from app.services.staff_auth import StaffSessionService
from app.tests.fakes import FakeRedis


class PrescriptionSetTestCase(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.redis = FakeRedis()
        app.dependency_overrides[get_redis] = lambda: self.redis

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        super().tearDown()

    async def make_staff(self, roles: list[str]) -> Staff:
        hospital = await Hospital.create(name="여성의원")
        return await Staff.create(
            hospital=hospital,
            login_id=f"user-{'-'.join(roles)}",
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

    async def test_returns_sets_in_stable_order(self) -> None:
        """목록을 준다. **차례가 흔들리지 않는다** — 매번 순서가 바뀌면
        스탭이 늘 고르던 자리를 눈으로 못 찾는다."""
        for name in ("자궁내막증 · 비잔 (계속)", "PCOS · 초진", "자궁내막증 · 통증관리"):
            await PrescriptionSet.create(name=name)

        staff = await self.make_staff(["staff"])
        async with self.client() as client:
            first = await client.get("/api/v1/prescription-sets", headers=await self.sign_in(staff))
            second = await client.get("/api/v1/prescription-sets", headers=await self.sign_in(staff))

        assert first.status_code == 200
        body = first.json()
        assert len(body) == 3
        assert {row["name"] for row in body} == {
            "자궁내막증 · 비잔 (계속)",
            "PCOS · 초진",
            "자궁내막증 · 통증관리",
        }

        ids = [row["prescription_set_id"] for row in body]
        assert ids == sorted(ids), f"차례가 오름차순이 아니다: {ids}"
        assert ids == [row["prescription_set_id"] for row in second.json()]

        # **차례를 코드가 못 박는가.** 위 두 줄만으로는 안 문다 — 정렬을 지워도
        # MySQL 이 대개 기본키 순으로 돌려주기 때문이다(우연히 맞는다).
        # 우연에 기대면 행이 지워지고 다시 생길 때 조용히 어긋난다.
        source = Path("app/catalog/api.py").read_text(encoding="utf-8")
        assert "order_by(" in source, "차례를 정하지 않는다 — 스탭이 늘 고르던 자리를 눈으로 못 찾는다"

    async def test_doctor_can_read_too(self) -> None:
        """의사도 본다. 스탭만 보면 의사 화면에서 처방을 고를 수 없다."""
        await PrescriptionSet.create(name="PCOS · 야즈 (계속)")
        staff = await self.make_staff(["doctor"])

        async with self.client() as client:
            res = await client.get("/api/v1/prescription-sets", headers=await self.sign_in(staff))

        assert res.status_code == 200
        assert len(res.json()) == 1

    async def test_requires_login(self) -> None:
        """로그인이 필요하다. 처방 세트 이름 자체가 이 의원이 무엇을 다루는지
        말해 주고, 그건 밖에 흘릴 것이 아니다."""
        await PrescriptionSet.create(name="자궁내막증 · 비잔 (처음)")

        async with self.client() as client:
            res = await client.get("/api/v1/prescription-sets")

        assert res.status_code in (401, 403), f"로그인 없이 목록이 새어 나갔다: {res.status_code}"

    async def test_empty_is_not_an_error(self) -> None:
        """아직 아무것도 안 정했으면 **빈 목록**이다. 404 로 두면 화면이
        「고장」으로 읽고, 설정에서 채우라는 안내를 못 띄운다."""
        staff = await self.make_staff(["staff"])

        async with self.client() as client:
            res = await client.get("/api/v1/prescription-sets", headers=await self.sign_in(staff))

        assert res.status_code == 200
        assert res.json() == []
