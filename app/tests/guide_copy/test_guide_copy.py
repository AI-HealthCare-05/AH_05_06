"""안내문 고치기 — KEY-234, 와이어프레임 D2-1 · D2-2.

원문 주석: 「의사마다 말하는 방식이 다르고 같은 의사도 일정하지 않다. 문구를
하나로 강제하면 원장님이 안 쓰신다. 대신 **원본을 위에 두어 무엇이 사실이고
무엇이 표현인지 보이게 한다.** 원본은 지워지지 않으므로 언제든 되돌아간다.」

**가장 크게 재는 것은 「원본을 손대지 않는가」다.** `drug_caution_content` 는
근거(출처 · 등급 · 검증일)와 승인이 붙은 자료라, 그것이 바뀌면 「무엇이
사실인가」를 잃는다.
"""

from datetime import date

from httpx import ASGITransport, AsyncClient
from tortoise.contrib.test import TestCase

from app.core.redis_client import get_redis
from app.core.utils.security import hash_password
from app.main import app
from app.models.catalog import (
    ApprovalStatus,
    CautionSectionKey,
    DoctorGuideCopy,
    DoctorGuideReview,
    DrugCautionContent,
    PrescriptionSet,
    SourceGrade,
)
from app.models.staffs import Hospital, Staff
from app.services.staff_auth import StaffSessionService
from app.tests.fakes import FakeRedis

ORIGIN = "[합성] 복용 초기에 두통, 구역, 유방압통이 나타날 수 있으며 대개 2~3개월 내 호전됩니다."
MINE = "처음 두세 달은 피가 조금씩 비칠 수 있어요. 대부분 저절로 좋아지니 그대로 드시면 됩니다."


class GuideCopyTestCase(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.redis = FakeRedis()
        app.dependency_overrides[get_redis] = lambda: self.redis

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        super().tearDown()

    async def a_set(self, name: str = "자궁내막증 · 비잔 (계속)") -> PrescriptionSet:
        return await PrescriptionSet.create(name=name)

    async def an_origin(
        self,
        row: PrescriptionSet,
        section: CautionSectionKey = CautionSectionKey.CAUTION,
        *,
        approved: bool = True,
        body: str = ORIGIN,
    ) -> DrugCautionContent:
        return await DrugCautionContent.create(
            prescription_set=row,
            section_key=section,
            body=body,
            source_name="합성 출처",
            source_org="합성 기관",
            source_url="https://example.invalid/synthetic",
            verified_at=date(2026, 1, 1),
            content_version="v1",
            source_grade=SourceGrade.A,
            approval_status=ApprovalStatus.APPROVED if approved else ApprovalStatus.DRAFT,
            approved_key=f"{row.prescription_set_id}:{section.value}" if approved else None,
        )

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
            response = await client.get("/api/v1/guide-copy", headers=await self.headers(staff), params=params)
        assert response.status_code == 200, response.text
        return response.json()

    async def save(self, staff: Staff, row: PrescriptionSet, body: str, section: str = "caution"):
        async with self.client() as client:
            return await client.put(
                f"/api/v1/guide-copy/{row.prescription_set_id}/{section}",
                headers=await self.headers(staff),
                json={"body": body},
            )

    @staticmethod
    def section(body: dict, set_id: int, key: str = "caution") -> dict:
        row = [item for item in body["items"] if item["prescription_set_id"] == set_id][0]
        return [part for part in row["sections"] if part["section_key"] == key][0]

    # ── 원본 ─────────────────────────────────────────────

    async def test_the_origin_shows_above(self) -> None:
        """원문: 「원본 / 식약처 허가사항」이 위에, 「원장님 문구」가 아래에."""
        row = await self.a_set()
        await self.an_origin(row)
        doctor = await self.a_staff(["doctor"], "origin")

        part = self.section(await self.fetch(doctor), row.prescription_set_id)

        assert part["origin"] == ORIGIN
        assert part["body"] is None, "고치기 전에는 원본이 그대로 나간다"

    async def test_only_an_approved_origin_counts(self) -> None:
        """초안을 「원본」이라 보이면 의사가 그것을 사실로 읽는다."""
        row = await self.a_set()
        await self.an_origin(row, approved=False)
        doctor = await self.a_staff(["doctor"], "draft")

        part = self.section(await self.fetch(doctor), row.prescription_set_id)

        assert part["origin"] is None

    async def test_saving_does_not_touch_the_origin(self) -> None:
        """**여기가 이 화면의 핵심이다.** 원본이 바뀌면 무엇이 사실인지 잃는다."""
        row = await self.a_set()
        origin = await self.an_origin(row)
        doctor = await self.a_staff(["doctor"], "untouched")

        await self.save(doctor, row, MINE)

        await origin.refresh_from_db()
        assert origin.body == ORIGIN
        assert origin.approval_status is ApprovalStatus.APPROVED
        assert origin.approved_key is not None, "승인 열쇠까지 그대로여야 한다"

    # ── 원장님 문구 ──────────────────────────────────────

    async def test_a_doctor_writes_their_own_words(self) -> None:
        row = await self.a_set()
        await self.an_origin(row)
        doctor = await self.a_staff(["doctor"], "mine")

        response = await self.save(doctor, row, MINE)

        assert response.status_code == 200
        part = self.section(response.json(), row.prescription_set_id)
        assert part["body"] == MINE
        assert part["origin"] == ORIGIN, "원본은 계속 위에 있다"

    async def test_reverting_deletes_the_row(self) -> None:
        """**원본을 베껴 넣지 않는다** — 그러면 원본이 개정돼도 되돌린 의사만
        옛 글을 계속 쓴다."""
        row = await self.a_set()
        await self.an_origin(row)
        doctor = await self.a_staff(["doctor"], "revert")
        await self.save(doctor, row, MINE)

        async with self.client() as client:
            response = await client.delete(
                f"/api/v1/guide-copy/{row.prescription_set_id}/caution",
                headers=await self.headers(doctor),
            )

        assert response.status_code == 200
        assert await DoctorGuideCopy.all().count() == 0
        assert self.section(response.json(), row.prescription_set_id)["body"] is None

    async def test_another_doctor_keeps_their_own(self) -> None:
        """원문: 「이 문구는 박연 원장 담당 환자에게만 발송됩니다」."""
        clinic = await Hospital.create(name="도로시여성의원")
        row = await self.a_set()
        await self.an_origin(row)
        mine = await self.a_staff(["doctor"], "two-mine", clinic, name="박연")
        theirs = await self.a_staff(["doctor"], "two-theirs", clinic, name="김연우")
        await self.save(mine, row, MINE)

        part = self.section(await self.fetch(theirs), row.prescription_set_id)

        assert part["body"] is None, "의사마다 따로다"

    # ── 🚨 잠금 ──────────────────────────────────────────

    async def test_the_emergency_line_never_opens(self) -> None:
        """원문: 「🚨 문구는 이 화면이 열리지 않는다」 · 「수정 불가」."""
        row = await self.a_set()
        await self.an_origin(row, CautionSectionKey.EMERGENCY)
        doctor = await self.a_staff(["doctor"], "locked")

        listed = self.section(await self.fetch(doctor), row.prescription_set_id, "emergency")
        response = await self.save(doctor, row, "고친 응급 문구", section="emergency")

        assert listed["editable"] is False
        assert response.status_code == 422 and response.json()["code"] == "SECTION_LOCKED"
        assert await DoctorGuideCopy.all().count() == 0

    async def test_an_empty_body_is_refused(self) -> None:
        row = await self.a_set()
        doctor = await self.a_staff(["doctor"], "empty")

        response = await self.save(doctor, row, "   ")

        assert response.status_code == 400 and response.json()["code"] == "EMPTY_BODY"

    # ── 확인 완료 ────────────────────────────────────────

    async def test_reviewing_marks_the_sheet(self) -> None:
        row = await self.a_set()
        doctor = await self.a_staff(["doctor"], "review")

        async with self.client() as client:
            response = await client.post(
                f"/api/v1/guide-copy/{row.prescription_set_id}/review",
                headers=await self.headers(doctor),
            )

        assert response.status_code == 200
        found = [item for item in response.json()["items"] if item["prescription_set_id"] == row.prescription_set_id][0]
        assert found["reviewed"] is True

    async def test_editing_after_a_review_unmarks_it(self) -> None:
        """**「확인 완료」가 붙은 채로 바뀐 글이 나가면 그 표시가 거짓말이 된다.**"""
        row = await self.a_set()
        await self.an_origin(row)
        doctor = await self.a_staff(["doctor"], "unmark")
        async with self.client() as client:
            await client.post(
                f"/api/v1/guide-copy/{row.prescription_set_id}/review",
                headers=await self.headers(doctor),
            )

        response = await self.save(doctor, row, MINE)

        found = [item for item in response.json()["items"] if item["prescription_set_id"] == row.prescription_set_id][0]
        assert found["reviewed"] is False
        assert await DoctorGuideReview.all().count() == 0

    # ── 권한 ─────────────────────────────────────────────

    async def test_staff_can_read_but_must_say_whose(self) -> None:
        """원문 부제: 「의사 계정만 · 스탭은 볼 수만 있다」."""
        clinic = await Hospital.create(name="도로시여성의원")
        row = await self.a_set()
        await self.an_origin(row)
        staff = await self.a_staff(["staff"], "readonly", clinic)
        doctor = await self.a_staff(["doctor"], "readonly-doc", clinic)

        async with self.client() as client:
            without = await client.get("/api/v1/guide-copy", headers=await self.headers(staff))

        assert without.status_code == 400 and without.json()["code"] == "DOCTOR_REQUIRED", (
            "「의원 공통 문구」라는 것이 없다 — 그 자리는 원본이다"
        )
        assert self.section(await self.fetch(staff, doctor_id=doctor.staff_id), row.prescription_set_id)["origin"]

        response = await self.save(staff, row, MINE)
        assert response.status_code == 403 and response.json()["code"] == "DOCTOR_ONLY"

    async def test_a_doctor_cannot_write_in_another_doctors_name(self) -> None:
        """문구가 그 의사 담당 환자에게 나간다 — 남의 이름으로 말하는 일이다."""
        clinic = await Hospital.create(name="도로시여성의원")
        row = await self.a_set()
        mine = await self.a_staff(["doctor"], "name-mine", clinic)
        theirs = await self.a_staff(["doctor"], "name-theirs", clinic)

        await self.save(mine, row, MINE)

        assert self.section(await self.fetch(theirs), row.prescription_set_id)["body"] is None
        assert await DoctorGuideCopy.filter(doctor_id=mine.staff_id).count() == 1

    async def test_another_clinic_does_not_see_the_words(self) -> None:
        mine = await Hospital.create(name="도로시여성의원")
        theirs = await Hospital.create(name="다른의원")
        row = await self.a_set()
        await self.an_origin(row)
        doctor = await self.a_staff(["doctor"], "scope-mine", mine)
        outsider = await self.a_staff(["doctor"], "scope-theirs", theirs)
        await self.save(doctor, row, MINE)

        part = self.section(await self.fetch(outsider), row.prescription_set_id)

        assert part["body"] is None, "남의 의원 문구가 새면 안 된다"
        assert part["origin"] == ORIGIN, "원본은 의원과 무관한 자료다"

    async def test_an_unknown_set_is_not_found(self) -> None:
        doctor = await self.a_staff(["doctor"], "nosuch")
        async with self.client() as client:
            response = await client.put(
                "/api/v1/guide-copy/999999/caution",
                headers=await self.headers(doctor),
                json={"body": MINE},
            )
        assert response.status_code == 404

    async def test_signed_out_cannot_look(self) -> None:
        async with self.client() as client:
            response = await client.get("/api/v1/guide-copy")
        assert response.status_code == 401
