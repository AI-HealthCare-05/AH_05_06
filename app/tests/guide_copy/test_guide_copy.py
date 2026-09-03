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
from app.services import guide_defaults
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
        """초안을 「원본」이라 보이면 의사가 그것을 사실로 읽는다.

        승인 안 된 자리는 **기본 문구**로 내려간다(`guide_defaults`). 빈칸이
        아니다 — 안내문 생성이 그때 쓰는 글이 그것이라, 빈칸을 보이면
        「원본이 없다」로 읽히는데 실제로는 나갈 글이 있다.
        """
        row = await self.a_set()
        await self.an_origin(row, approved=False)
        doctor = await self.a_staff(["doctor"], "draft")

        part = self.section(await self.fetch(doctor), row.prescription_set_id)

        assert part["origin"] != ORIGIN, "초안이 원본으로 나갔다"
        assert part["origin"] == guide_defaults.CAUTION, "기본 문구가 아니다"

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

    async def test_every_doctor_sees_the_same_wording(self) -> None:
        """**문구는 의원 공통이다** (2026-09-02 회의).

        원문 D2-2 는 「이 문구는 박연 원장 담당 환자에게만 발송됩니다」라 적어
        의사마다 따로 두었다. 그런데 회의에서 「기본 설정은 모두 공통으로 두자.
        원장별 설정은 나중에」로 정했다.

        개인 것만 두면 이렇게 됐다: 원장 A 가 고치면 A 담당 환자에게만 나가고,
        원장 B 가 같은 처방을 열면 약·일수·확인 항목은 A 가 정한 그대로인데
        **문구만 기본값으로 보인다.** B 는 「아직 아무도 안 고쳤구나」로 읽는다.
        처방 세트가 의원 공통인데 그 위에 덧씌우는 표현만 개인 것이면 화면이
        한 처방을 두 가지로 말하게 된다.
        """
        clinic = await Hospital.create(name="도로시여성의원")
        row = await self.a_set()
        await self.an_origin(row)
        mine = await self.a_staff(["doctor"], "two-mine", clinic, name="박연")
        theirs = await self.a_staff(["doctor"], "two-theirs", clinic, name="김연우")
        await self.save(mine, row, MINE)

        part = self.section(await self.fetch(theirs), row.prescription_set_id)

        assert part["body"] == MINE, "다른 원장에게 안 보인다 — 의원 공통이 아니다"

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

    async def test_staff_opens_their_own_and_can_write_it(self) -> None:
        """**스탭도 제 문구를 갖는다** — 2026-09-02 회의에서 설정 수정 권한을
        열었다. 원문 D2-2 는 「의사 계정만 · 스탭은 볼 수만 있다」였다.

        전에는 스탭이 번호 없이 열면 `400 DOCTOR_REQUIRED` 였다. 그런데
        **화면에는 고르는 칸이 없어서**, 스탭이 이 화면을 열면 그냥
        「불러오지 못했습니다」가 떴다 — 아무도 못 쓰는 화면이었다.
        """
        clinic = await Hospital.create(name="도로시여성의원")
        row = await self.a_set()
        await self.an_origin(row)
        staff = await self.a_staff(["staff"], "readonly", clinic)

        async with self.client() as client:
            mine = await client.get("/api/v1/guide-copy", headers=await self.headers(staff))

        assert mine.status_code == 200, "번호를 안 줘도 제 것을 준다"
        assert self.section(mine.json(), row.prescription_set_id)["origin"], "원본이 보여야 한다"

        response = await self.save(staff, row, MINE)
        assert response.status_code == 200, response.text

    async def test_someone_elses_wording_cannot_even_be_addressed(self) -> None:
        """**역할 문은 열렸어도 남의 것은 못 고친다.**

        막는 방식이 검사가 아니라 **모양**이다 — 저장 경로가 `doctor_id` 를
        아예 안 받는다(`_writer(actor)` 가 늘 자기 번호를 준다). 겨눌 수
        없으면 실수로도 못 고친다. 물어보는 칸을 두고 검사로 막는 것보다
        낫다: 검사는 빠질 수 있어도 없는 칸은 안 생긴다.

        지금은 **모든 저장이 의원 공통 줄로 간다**(2026-09-02 회의). 그래도
        이 모양은 그대로 값이 있다 — 원장별 문구를 나중에 열 때, 겨누는 칸을
        새로 만들지 않으면 남의 이름으로 쓸 길이 생기지 않는다.
        """
        clinic = await Hospital.create(name="도로시여성의원")
        row = await self.a_set()
        await self.an_origin(row)
        staff = await self.a_staff(["staff"], "nosy", clinic)
        doctor = await self.a_staff(["doctor"], "owner-doc", clinic)

        async with self.client() as client:
            # 남의 번호를 붙여 봐도 무시된다 — 받는 칸이 없다.
            # (지금은 의원 공통 줄에 앉는다.)
            response = await client.put(
                f"/api/v1/guide-copy/{row.prescription_set_id}/caution",
                headers=await self.headers(staff),
                params={"doctor_id": doctor.staff_id},
                json={"body": MINE},
            )

        assert response.status_code == 200, response.text
        assert response.json()["doctor_id"] is None, "남의 번호가 먹혔다 — 의원 공통이어야 한다"

        # 그 의사 **개인** 자리는 비어 있어야 한다.
        theirs = await self.fetch(doctor, doctor_id=doctor.staff_id)
        assert not self.section(theirs, row.prescription_set_id)["body"], "스탭이 고친 글이 의사 개인 자리에 들어갔다"

    async def test_writing_lands_on_the_clinic_row_not_a_personal_one(self) -> None:
        """**고친 것은 의원 공통 줄에 앉는다.**

        개인 줄에 앉으면 고친 사람만 보게 되고, 다시 열었을 때 화면은 공통을
        보이므로 **안 바뀐 것처럼 읽힌다.** 읽는 자리와 쓰는 자리가 같아야 한다.
        """
        clinic = await Hospital.create(name="도로시여성의원")
        row = await self.a_set()
        mine = await self.a_staff(["doctor"], "name-mine", clinic)
        theirs = await self.a_staff(["doctor"], "name-theirs", clinic)

        await self.save(mine, row, MINE)

        assert self.section(await self.fetch(theirs), row.prescription_set_id)["body"] == MINE
        assert await DoctorGuideCopy.filter(doctor_id=None).count() == 1, "의원 공통 줄이 아니다"
        assert await DoctorGuideCopy.filter(doctor_id=mine.staff_id).count() == 0, "개인 줄이 생겼다"

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

    async def test_the_page_carries_the_base_wording(self) -> None:
        """**아직 없는 처방도 무슨 글이 나갈지 보여야 한다.**

        만들기 화면은 세트 번호가 없어 `items` 에서 제 줄을 못 찾는다. 그래서
        갈래별 기본 문구를 따로 싣는다.

        화면이 문장을 베껴 두면 두 곳이 갈라진다 — 한동안 `guides.py` 가 제
        것을 따로 들고 있어서 설정 화면이 **실제로는 나가지 않는 글**을
        원본이라며 보였다. 그 사고를 되풀이하지 않으려고 서버가 준다.
        """
        clinic = await Hospital.create(name="도로시여성의원")
        staff = await self.a_staff(["staff"], "defaults", clinic)

        page = await self.fetch(staff)

        got = {row["section_key"]: row for row in page["defaults"]}
        assert set(got) == {"medication", "caution", "emergency", "life"}
        assert got["medication"]["body"] == guide_defaults.MEDICATION
        assert got["life"]["body"] == guide_defaults.LIFE
        assert got["emergency"]["editable"] is False, "🚨 는 고칠 수 없다(KEY-150)"
        assert got["caution"]["editable"] is True
